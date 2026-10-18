"""The kill-switch flag's format and its fail-closed reader (Law 15; ADR-006 sections 1, 3, 4; D27;
docs/tasks/M4-04.md rules 1 and 2).

The flag is canonical JSON in `<data dir>/control/trading_enabled.json`:

    {"schema": 1, "trading_enabled": bool, "sequence": int, "changed_at": ISO UTC, "changed_by": str,
     "verified": bool, "reason": str, "checksum": SHA-256 of the canonical form of the other fields}

`KillSwitchReader.read()` never raises. A missing, unreadable, malformed,
wrong-schema, non-boolean or bad-checksum flag reads as **disabled**, with a
distinct problem: anything the gate can't trust stops new submissions. The flag
starts out missing, so trading is disabled until an Admin resumes it.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from investment_engine.lineage.records import register

SCHEMA = 1
FLAG_FILE = "trading_enabled.json"
JOURNAL_FILE = "kill_switch_journal.jsonl"
LOCK_FILE = "kill_switch.lock"
_FIELDS = ("schema", "trading_enabled", "sequence", "changed_at", "changed_by", "verified", "reason")


@dataclass(frozen=True)
class FlagState:
    trading_enabled: bool
    sequence: int
    changed_at: datetime
    changed_by: str
    verified: bool  # False: an emergency halt whose operator couldn't be checked (database unavailable)
    reason: str


@dataclass(frozen=True)
class FlagReading:
    enabled: bool
    state: FlagState | None
    problem: str | None  # set -> enabled is False


register(FlagState)
register(FlagReading)


def _canonical(fields: dict) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def encode_flag(state: FlagState) -> str:
    fields = {"schema": SCHEMA, "trading_enabled": state.trading_enabled, "sequence": state.sequence,
              "changed_at": state.changed_at.isoformat(), "changed_by": state.changed_by,
              "verified": state.verified, "reason": state.reason}
    checksum = hashlib.sha256(_canonical(fields).encode()).hexdigest()
    return _canonical({**fields, "checksum": checksum}) + "\n"


def decode_flag(text: str) -> FlagReading:
    try:
        data = json.loads(text)
    except ValueError:
        return FlagReading(False, None, "malformed: not JSON")
    if not isinstance(data, dict):
        return FlagReading(False, None, "malformed: not an object")
    if data.get("schema") != SCHEMA:
        return FlagReading(False, None, f"wrong schema {data.get('schema')!r}")
    if set(data) != {*_FIELDS, "checksum"}:
        return FlagReading(False, None, "wrong fields")
    if not isinstance(data["trading_enabled"], bool):
        return FlagReading(False, None, "trading_enabled is not a boolean")
    expected = hashlib.sha256(_canonical({k: data[k] for k in _FIELDS}).encode()).hexdigest()
    if data["checksum"] != expected:
        return FlagReading(False, None, "bad checksum")
    try:
        state = FlagState(data["trading_enabled"], int(data["sequence"]), datetime.fromisoformat(data["changed_at"]),
                          str(data["changed_by"]), bool(data["verified"]), str(data["reason"]))
    except (TypeError, ValueError):
        return FlagReading(False, None, "malformed: bad field values")
    if state.changed_at.tzinfo is None or isinstance(data["sequence"], bool) or state.sequence < 1:
        return FlagReading(False, None, "malformed: bad field values")
    if not state.trading_enabled:
        return FlagReading(False, state, None)
    return FlagReading(True, state, None)


class KillSwitchReader:
    """Read-only. The Execution Worker holds one of these and nothing that writes (ADR-006 section 3)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read(self) -> FlagReading:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return FlagReading(False, None, "missing")
        except OSError as exc:
            return FlagReading(False, None, f"unreadable ({type(exc).__name__})")
        except UnicodeDecodeError:
            return FlagReading(False, None, "malformed: not UTF-8")
        return decode_flag(text)


__all__ = ["FLAG_FILE", "JOURNAL_FILE", "LOCK_FILE", "SCHEMA", "FlagReading", "FlagState", "KillSwitchReader",
           "decode_flag", "encode_flag"]
