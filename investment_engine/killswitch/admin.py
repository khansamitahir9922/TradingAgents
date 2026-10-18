"""Writing the kill-switch flag: the lock, the journal, recovery and the failure rules (Law 15; ADR-006; D27, D28;
PRD section 4, UC-06; docs/tasks/M4-04.md rules 3–7). Imported only by the Admin CLI.

Every change, and `sync_audit`, runs under an exclusive OS lock on
`kill_switch.lock` (msvcrt on Windows, fcntl elsewhere), so sequences never
collide and nothing needs the database. The OS releases the lock if its holder
dies; waiting is bounded at 10 seconds.

Replacing the flag file is the **publication point**: once `os.replace`
returns, the change has happened, because a worker may already have read it.
Under the lock, in order:

1. resolve outstanding intents (every INTENT without an APPLIED or
   NOT_APPLIED line) against the current flag, before anything is
   overwritten: APPLIED (recovered) when the flag shows that sequence;
   NOT_APPLIED only when a readable flag shows a lower one (sequences only
   grow, so it was never published); otherwise UNRESOLVED: a missing or
   unreadable flag, or a later sequence published by an emergency halt. A
   missing flag is never proof that nothing was published: the file could
   have been lost after it (Codex M4 review B8). UNRESOLVED is not a
   resolution: the intent is checked again every time, recorded once, and
   becomes APPLIED if the flag later proves it. A readable flag whose sequence
   was never journalled is recorded as APPLIED (recovered; intent not
   journalled). History is never invented;
2. allocate the next sequence: 1 + the highest in the flag or any complete
   journal line;
3. append INTENT;  4. publish the flag;  5. append APPLIED;
6. release the lock; the caller then writes the audit event if it can.

Failure rules (rule 5): a halt is always published if the flag can be written,
whatever happened to the journal, and the result says what is incomplete; a
resume is refused if anything before publication fails, and reported as
applied (never refused) if journalling fails after it. A flag write that this
process saw fail is journalled NOT_APPLIED at once: the one moment that
proves it. A resume is refused while any earlier change is UNRESOLVED, on
every retry; a halt is never blocked. A journal line never proves the flag
changed; only the flag's own sequence does.

Only an active Admin may change the flag (PRD section 4, UC-06). The caller
verifies that in the database. If the database is unreachable, a halt is
still applied, marked "identity unverified": a fail-safe stop, not a granted
right. A resume always needs verification.
"""

import contextlib
import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from investment_engine.killswitch.flag import (
    FLAG_FILE,
    JOURNAL_FILE,
    LOCK_FILE,
    FlagReading,
    FlagState,
    KillSwitchReader,
    encode_flag,
)
from investment_engine.market.availability import check_utc

LOCK_WAIT_SECONDS = 10
RESOLUTIONS = ("APPLIED", "NOT_APPLIED", "UNRESOLVED")
FINAL = ("APPLIED", "NOT_APPLIED")  # UNRESOLVED is recorded, but the intent stays outstanding (B8)


class KillSwitchRefused(RuntimeError):
    """The change was not made; the message says why."""


@dataclass(frozen=True)
class ChangeResult:
    applied: bool
    sequence: int
    journal: str  # "recorded" | "FAILED: <why>"
    history: str  # "complete" | "incomplete: <what>"


@dataclass(frozen=True)
class JournalEntry:
    sequence: int
    phase: str  # INTENT | APPLIED | NOT_APPLIED | UNRESOLVED
    data: dict


def _canonical(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class KillSwitchAdmin:
    def __init__(self, control_dir: Path, *, clock) -> None:
        self.dir, self._clock = Path(control_dir), clock
        self.flag_path = self.dir / FLAG_FILE
        self.journal_path = self.dir / JOURNAL_FILE
        self.lock_path = self.dir / LOCK_FILE
        self.warnings: list[str] = []

    # ---------------------------------------------------------------- the lock

    @contextmanager
    def lock(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        handle = open(self.lock_path, "a+b")  # noqa: SIM115 - held for the whole critical section
        try:
            deadline = time.monotonic() + LOCK_WAIT_SECONDS
            while True:
                try:
                    _try_lock(handle)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise KillSwitchRefused("the kill-switch lock is held by another Admin CLI; nothing was "
                                                "changed. Try again.") from None
                    time.sleep(0.05)
            try:
                yield
            finally:
                _unlock(handle)
        finally:
            handle.close()

    # ---------------------------------------------------------------- the journal

    def entries(self) -> list[JournalEntry]:
        """Complete journal lines; a truncated or malformed line is skipped with a warning (rule 6)."""
        try:
            text = self.journal_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        lines = text.split("\n")
        entries = []
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                entries.append(JournalEntry(int(data["seq"]), str(data["phase"]), data))
            except (ValueError, KeyError, TypeError):
                last = number == len(lines)
                self.warnings.append(f"journal line {number} is {'a truncated tail' if last else 'malformed'}; "
                                     "ignored")
        return entries

    def _append(self, data: dict) -> None:
        with open(self.journal_path, "a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell():
                handle.seek(-1, os.SEEK_END)
                if handle.read(1) != b"\n":  # a truncated tail: start a fresh line
                    handle.write(b"\n")
            handle.write((_canonical(data) + "\n").encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())

    def _publish(self, state: FlagState) -> None:
        temporary = self.dir / (FLAG_FILE + ".tmp")
        with open(temporary, "wb") as handle:
            handle.write(encode_flag(state).encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.flag_path)

    def read(self) -> FlagReading:
        return KillSwitchReader(self.flag_path).read()

    # ---------------------------------------------------------------- step 1: resolution

    def _resolve(self, now: datetime) -> tuple[list[str], int]:
        """Resolve outstanding intents against the current flag; returns (what couldn't be recorded, how many
        were found UNRESOLVED now)."""
        entries = self.entries()
        resolved = {e.sequence for e in entries if e.phase in FINAL}
        intents = sorted({e.sequence for e in entries if e.phase == "INTENT"} - resolved)
        already_unresolved = {e.sequence for e in entries if e.phase == "UNRESOLVED"}
        reading = self.read()
        flag_seq = reading.state.sequence if reading.state is not None else None
        problems = []
        lines = []
        for seq in intents:
            if flag_seq is None:  # missing or unreadable: never evidence that nothing was published
                lines.append({"seq": seq, "phase": "UNRESOLVED", "why": f"flag unreadable ({reading.problem})"})
            elif flag_seq == seq:
                lines.append({"seq": seq, "phase": "APPLIED", "recovered": True})
            elif flag_seq < seq:
                lines.append({"seq": seq, "phase": "NOT_APPLIED", "why": f"the flag shows {flag_seq}"})
            else:  # a later flag never proves an earlier change didn't happen
                lines.append({"seq": seq, "phase": "UNRESOLVED", "why": f"the flag already shows later {flag_seq}"})
        journalled = {e.sequence for e in entries}
        if flag_seq is not None and flag_seq not in journalled:
            lines.append({"seq": flag_seq, "phase": "APPLIED", "recovered": True, "intent_journalled": False,
                          "state": {"trading_enabled": reading.state.trading_enabled,
                                    "changed_by": reading.state.changed_by, "verified": reading.state.verified,
                                    "reason": reading.state.reason, "changed_at": reading.state.changed_at.isoformat()}})
        for line in lines:
            if line["phase"] == "UNRESOLVED" and line["seq"] in already_unresolved:
                continue  # recorded once; it stays outstanding and counts against a resume
            try:
                self._append({**line, "resolved_at": now.isoformat()})
            except OSError as exc:
                problems.append(f"sequence {line['seq']} resolution not journalled ({type(exc).__name__})")
        return problems, sum(1 for line in lines if line["phase"] == "UNRESOLVED")

    # ---------------------------------------------------------------- changes

    def _change(self, *, enable: bool, operator: str, verified: bool, reason: str) -> ChangeResult:
        if not isinstance(reason, str) or not reason.strip():
            raise KillSwitchRefused("a halt or resume needs a reason")
        if enable and not verified:
            raise KillSwitchRefused("a resume needs an Admin verified in the database; nothing was changed")
        now = check_utc(self._clock.now(), "now")
        with self.lock():
            problems, unresolved = self._resolve(now)
            if enable and (problems or unresolved):
                why = "; ".join(problems) or f"{unresolved} earlier change(s) UNRESOLVED"
                raise KillSwitchRefused(f"earlier changes couldn't be established ({why}); a resume is refused, "
                                        "and stays refused until the flag establishes them. A halt still works. "
                                        "Retrying is not an acknowledgement")
            reading = self.read()
            sequences = [e.sequence for e in self.entries()]
            if reading.state is not None:
                sequences.append(reading.state.sequence)
            sequence = 1 + max(sequences, default=0)
            state = FlagState(enable, sequence, now, operator, verified, reason)
            journal = "recorded"
            details = {"op": "resume" if enable else "halt", "trading_enabled": enable, "changed_by": operator,
                       "verified": verified, "reason": reason, "changed_at": now.isoformat()}
            try:
                self._append({"seq": sequence, "phase": "INTENT", **details})
            except OSError as exc:
                if enable:
                    raise KillSwitchRefused(f"the journal couldn't be written ({type(exc).__name__}); a resume is "
                                            "refused and nothing was changed") from None
                journal = f"FAILED: intent not journalled ({type(exc).__name__})"
            try:
                self._publish(state)
            except OSError as exc:
                # Observed here, so proven: nothing was published (B8). If this line can't be written either, the
                # next step 1 finds the intent outstanding.
                with contextlib.suppress(OSError):
                    self._append({"seq": sequence, "phase": "NOT_APPLIED", "why": f"the flag write failed "
                                  f"({type(exc).__name__})", "resolved_at": now.isoformat()})
                raise KillSwitchRefused(f"the flag couldn't be written ({type(exc).__name__}); nothing was "
                                        "applied") from None
            try:
                self._append({"seq": sequence, "phase": "APPLIED", **details})  # self-contained if INTENT failed
            except OSError as exc:
                journal = f"FAILED: applied, but not journalled as applied ({type(exc).__name__})"
                problems.append(f"sequence {sequence} applied but not journalled")
        history = "complete" if not problems and journal == "recorded" else "incomplete: " + "; ".join(
            problems or [journal])
        return ChangeResult(True, sequence, journal, history)

    def halt(self, *, operator: str, verified: bool, reason: str) -> ChangeResult:
        return self._change(enable=False, operator=operator, verified=verified, reason=reason)

    def resume(self, *, operator: str, verified: bool, reason: str) -> ChangeResult:
        return self._change(enable=True, operator=operator, verified=verified, reason=reason)

    # ---------------------------------------------------------------- audit

    def sync_audit(self, record) -> list[str]:
        """Under the lock, resolve, then pass each journalled outcome to `record(sequence, phase, data)`
        (the caller's idempotent audit writer). Returns the phases passed, in sequence order."""
        now = check_utc(self._clock.now(), "now")
        with self.lock():
            self._resolve(now)
            entries = self.entries()
        intents = {e.sequence: e.data for e in entries if e.phase == "INTENT"}
        done = []
        for entry in sorted((e for e in entries if e.phase in RESOLUTIONS), key=lambda e: e.sequence):
            data = {**intents.get(entry.sequence, {}), **entry.data}
            record(entry.sequence, entry.phase, data)
            done.append(f"{entry.sequence}:{entry.phase}")
        return done


if sys.platform == "win32":
    import msvcrt

    def _try_lock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def audit_event(sequence: int, phase: str, data: dict):
    """The audit event for one journalled outcome. Deterministic (its time is the change's own), so the event
    written right after a change and the one `sync-audit` writes later are the same event (rule 7)."""
    from investment_engine.audit.events import Actor, ActorKind, AuditEvent

    when = datetime.fromisoformat(data.get("changed_at") or data.get("resolved_at"))
    operator, verified = str(data.get("changed_by", "unknown")), bool(data.get("verified", False))
    actor = (Actor(ActorKind.OPERATOR, operator, "ADMIN", None) if verified
             else Actor(ActorKind.PROCESS, "admin-cli", None, None))
    if phase == "APPLIED":
        action = "killswitch.resume" if data.get("trading_enabled") else "killswitch.halt"
    else:
        action = f"killswitch.{phase.lower()}"
    reason = str(data.get("reason") or data.get("why") or phase)
    if not verified:
        reason = f"operator claimed {operator}; identity unverified. {reason}"
    return AuditEvent(actor, action, "kill_switch", "trading", None, _canonical(data), when, None, reason[:1000],
                      f"killswitch:{sequence}", f"killswitch:{sequence}:{phase}")


__all__ = ["ChangeResult", "JournalEntry", "KillSwitchAdmin", "KillSwitchRefused", "audit_event"]
