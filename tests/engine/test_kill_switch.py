"""The kill-switch flag, its lock, journal and failure rules (docs/tasks/M4-04.md rules 1–7; ADR-006; D27, D28)."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.killswitch import admin as admin_module
from investment_engine.killswitch.admin import KillSwitchAdmin, KillSwitchRefused
from investment_engine.killswitch.flag import FlagState, KillSwitchReader, encode_flag

NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)
ROOT = Path(__file__).parents[2]


@pytest.fixture
def ks(tmp_path):
    return KillSwitchAdmin(tmp_path / "control", clock=ReplayClock(NOW))


def phases(ks):
    return [(e.sequence, e.phase) for e in ks.entries()]


# ---------------------------------------------------------------- reading fails closed (rule 2)


@pytest.mark.unit
@pytest.mark.parametrize("content, problem", [
    (None, "missing"),
    ("{not json", "malformed: not JSON"),
    ("[1, 2]", "malformed: not an object"),
    (json.dumps({"schema": 2}), "wrong schema 2"),
    (json.dumps({"schema": 1, "trading_enabled": True}), "wrong fields"),
], ids=["missing", "not-json", "not-object", "schema", "fields"])
def test_every_bad_flag_reads_as_disabled(tmp_path, content, problem):
    path = tmp_path / "trading_enabled.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    reading = KillSwitchReader(path).read()
    assert (reading.enabled, reading.problem) == (False, problem)


@pytest.mark.unit
def test_a_tampered_or_non_boolean_flag_reads_as_disabled(tmp_path):
    path = tmp_path / "trading_enabled.json"
    good = encode_flag(FlagState(True, 1, NOW, "owner", True, "go"))
    path.write_text(good, encoding="utf-8")
    assert KillSwitchReader(path).read().enabled is True
    path.write_text(good.replace('"reason":"go"', '"reason":"gone"'), encoding="utf-8")
    assert KillSwitchReader(path).read().problem == "bad checksum"
    path.write_text(good.replace('"trading_enabled":true', '"trading_enabled":"yes"'), encoding="utf-8")
    assert KillSwitchReader(path).read().problem == "trading_enabled is not a boolean"
    path.write_bytes(b"\xff\xfe")
    assert KillSwitchReader(path).read().enabled is False


# ---------------------------------------------------------------- changes (rules 3, 4)


@pytest.mark.unit
def test_halt_then_resume_journal_and_publish_in_order(ks):
    assert ks.read().problem == "missing"  # starts disabled
    halt = ks.halt(operator="owner", verified=True, reason="stop")
    resume = ks.resume(operator="owner", verified=True, reason="go")
    assert (halt.sequence, resume.sequence) == (1, 2) and halt.history == resume.history == "complete"
    assert phases(ks) == [(1, "INTENT"), (1, "APPLIED"), (2, "INTENT"), (2, "APPLIED")]
    reading = ks.read()
    assert reading.enabled and reading.state.sequence == 2


@pytest.mark.unit
def test_an_unverified_halt_applies_but_an_unverified_resume_is_refused(ks):
    result = ks.halt(operator="owner", verified=False, reason="database down")
    assert result.applied and ks.read().state.verified is False
    with pytest.raises(KillSwitchRefused, match="verified"):
        ks.resume(operator="owner", verified=False, reason="go")
    assert ks.read().state.sequence == 1


@pytest.mark.unit
def test_concurrent_writers_in_separate_processes_never_share_a_sequence(tmp_path):
    script = (
        "import sys\n"
        "from datetime import UTC, datetime\n"
        "from pathlib import Path\n"
        "from investment_engine.clock import ReplayClock\n"
        "from investment_engine.killswitch.admin import KillSwitchAdmin\n"
        "ks = KillSwitchAdmin(Path(sys.argv[1]), clock=ReplayClock(datetime(2026, 10, 18, 12, tzinfo=UTC)))\n"
        "for _ in range(10):\n"
        "    ks.halt(operator='owner', verified=True, reason=sys.argv[2])\n"
    )
    control = tmp_path / "control"
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    procs = [subprocess.Popen([sys.executable, "-c", script, str(control), name], cwd=ROOT, env=env)
             for name in ("a", "b")]
    for p in procs:
        assert p.wait(timeout=120) == 0
    ks = KillSwitchAdmin(control, clock=ReplayClock(NOW))
    applied = [s for s, phase in phases(ks) if phase == "APPLIED"]
    assert sorted(applied) == list(range(1, 21)) and ks.read().state.sequence == 20


# ---------------------------------------------------------------- crashes and failures (rule 5)


def _fail_on(monkeypatch, ks, *, phase=None, publish=False, error=OSError):
    real_append, real_publish = ks._append, ks._publish

    def append(data):
        if phase is not None and data.get("phase") in phase:
            raise error("injected")
        return real_append(data)

    def publish_(state):
        if publish:
            raise error("injected")
        return real_publish(state)

    monkeypatch.setattr(ks, "_append", append)
    monkeypatch.setattr(ks, "_publish", publish_)


@pytest.mark.unit
def test_a_crash_after_intent_with_no_flag_stays_unresolved_and_a_resume_stays_refused(ks, monkeypatch):
    """B8 (Codex M4 review): a missing flag never proves that nothing was published; the file could have been lost
    after a publication. The outcome can't be established, so it stays UNRESOLVED; a halt still works."""
    _fail_on(monkeypatch, ks, publish=True, error=KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        ks.halt(operator="owner", verified=True, reason="stop")
    monkeypatch.undo()
    ks.halt(operator="owner", verified=True, reason="stop again")
    assert phases(ks) == [(1, "INTENT"), (1, "UNRESOLVED"), (2, "INTENT"), (2, "APPLIED")]
    for _ in range(2):  # a retry is not an acknowledgement
        with pytest.raises(KillSwitchRefused, match="UNRESOLVED"):
            ks.resume(operator="owner", verified=True, reason="go")
    assert [p for s, p in phases(ks) if s == 1] == ["INTENT", "UNRESOLVED"]  # recorded once, still outstanding
    assert ks.read().enabled is False


@pytest.mark.unit
def test_a_crash_after_intent_with_an_older_readable_flag_is_resolved_not_applied(ks, monkeypatch):
    ks.halt(operator="owner", verified=True, reason="first")
    _fail_on(monkeypatch, ks, publish=True, error=KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        ks.resume(operator="owner", verified=True, reason="crashes before publishing")
    monkeypatch.undo()
    ks.resume(operator="owner", verified=True, reason="go")  # the flag still shows 1 < 2: proven not applied
    assert phases(ks)[2:] == [(2, "INTENT"), (2, "NOT_APPLIED"), (3, "INTENT"), (3, "APPLIED")]
    assert ks.read().enabled is True


@pytest.mark.unit
def test_a_lost_applied_line_then_a_lost_flag_is_never_guessed_not_applied(ks):
    """B8: a resume published, its APPLIED line lost, then the flag lost: recovery must not write NOT_APPLIED."""
    ks.resume(operator="owner", verified=True, reason="published")
    first = ks.journal_path.read_text(encoding="utf-8").splitlines()[0]
    ks.journal_path.write_text(first + "\n", encoding="utf-8")
    ks.flag_path.unlink()
    with pytest.raises(KillSwitchRefused, match="UNRESOLVED"):
        ks.resume(operator="owner", verified=True, reason="must not guess")
    assert [p for s, p in phases(ks) if s == 1] == ["INTENT", "UNRESOLVED"]


@pytest.mark.unit
def test_unresolved_history_after_a_malformed_flag_cannot_be_bypassed_by_a_retry(ks):
    ks.resume(operator="owner", verified=True, reason="published")
    first = ks.journal_path.read_text(encoding="utf-8").splitlines()[0]
    ks.journal_path.write_text(first + "\n", encoding="utf-8")
    ks.flag_path.write_text("malformed", encoding="utf-8")
    for _ in range(2):
        with pytest.raises(KillSwitchRefused, match="UNRESOLVED"):
            ks.resume(operator="owner", verified=True, reason="retry")
    ks.halt(operator="owner", verified=True, reason="a halt still works")
    assert ks.read().enabled is False and ks.read().state.sequence == 2


@pytest.mark.unit
def test_an_unresolved_intent_is_resolved_once_the_flag_proves_it(ks):
    ks.resume(operator="owner", verified=True, reason="published")
    first = ks.journal_path.read_text(encoding="utf-8").splitlines()[0]
    ks.journal_path.write_text(first + "\n", encoding="utf-8")
    good = ks.flag_path.read_text(encoding="utf-8")
    ks.flag_path.write_text("malformed", encoding="utf-8")
    with pytest.raises(KillSwitchRefused, match="UNRESOLVED"):
        ks.resume(operator="owner", verified=True, reason="unreadable now")
    ks.flag_path.write_text(good, encoding="utf-8")  # the flag is readable again and shows sequence 1
    ks.resume(operator="owner", verified=True, reason="established now")
    assert [p for s, p in phases(ks) if s == 1] == ["INTENT", "UNRESOLVED", "APPLIED"]


@pytest.mark.unit
def test_seven_then_eight_the_earlier_publication_is_resolved_before_it_is_overwritten(ks, monkeypatch):
    for _ in range(6):
        ks.halt(operator="owner", verified=True, reason="x")
    _fail_on(monkeypatch, ks, phase=("APPLIED",), error=KeyboardInterrupt)  # crash after publishing 7
    with pytest.raises(KeyboardInterrupt):
        ks.halt(operator="owner", verified=True, reason="seven")
    monkeypatch.undo()
    assert ks.read().state.sequence == 7
    ks.resume(operator="owner", verified=True, reason="eight")
    tail = phases(ks)[-4:]
    assert tail == [(7, "INTENT"), (7, "APPLIED"), (8, "INTENT"), (8, "APPLIED")]
    assert next(e for e in ks.entries() if e.sequence == 7 and e.phase == "APPLIED").data["recovered"] is True
    recorded = []
    ks.sync_audit(lambda seq, phase, data: recorded.append((seq, phase, data.get("reason"))))
    assert recorded[-2:] == [(7, "APPLIED", "seven"), (8, "APPLIED", "eight")]


@pytest.mark.unit
@pytest.mark.parametrize("op", ["halt", "resume"])
def test_an_intent_journal_failure(ks, monkeypatch, op):
    if op == "resume":
        ks.halt(operator="owner", verified=True, reason="setup")
    _fail_on(monkeypatch, ks, phase=("INTENT",))
    if op == "halt":
        result = ks.halt(operator="owner", verified=True, reason="stop")
        assert result.applied and result.journal.startswith("FAILED") and ks.read().state.sequence == 1
        monkeypatch.undo()
        ks.halt(operator="owner", verified=True, reason="again")
        assert [p for s, p in phases(ks) if s == 1] == ["APPLIED"]  # no INTENT line, but a self-contained APPLIED
        recorded = []
        ks.sync_audit(lambda seq, phase, data: recorded.append(admin_module.audit_event(seq, phase, data)))
        assert recorded[0].reason == "stop" and recorded[0].action == "killswitch.halt"
    else:
        with pytest.raises(KillSwitchRefused, match="resume is refused"):
            ks.resume(operator="owner", verified=True, reason="go")
        assert ks.read().state.sequence == 1 and ks.read().enabled is False


@pytest.mark.unit
@pytest.mark.parametrize("op", ["halt", "resume"])
def test_an_applied_journal_failure_is_reported_applied_never_refused(ks, monkeypatch, op):
    _fail_on(monkeypatch, ks, phase=("APPLIED",))
    result = getattr(ks, op)(operator="owner", verified=True, reason="x")
    assert result.applied and "applied, but not journalled" in result.journal and result.history.startswith(
        "incomplete")
    assert ks.read().state.sequence == 1 and ks.read().enabled is (op == "resume")


@pytest.mark.unit
def test_a_flag_write_failure_applies_nothing(ks, monkeypatch):
    _fail_on(monkeypatch, ks, publish=True)
    with pytest.raises(KillSwitchRefused, match="nothing was applied"):
        ks.halt(operator="owner", verified=True, reason="x")
    monkeypatch.undo()
    assert ks.read().problem == "missing"
    # The process saw the write fail, which proves nothing was published: NOT_APPLIED at once, never a guess later.
    assert phases(ks) == [(1, "INTENT"), (1, "NOT_APPLIED")]
    ks.resume(operator="owner", verified=True, reason="go")
    assert ks.read().enabled is True


@pytest.mark.unit
def test_an_unrecordable_resolution_refuses_a_resume_but_a_halt_still_publishes(ks, monkeypatch):
    _fail_on(monkeypatch, ks, publish=True, error=KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        ks.halt(operator="owner", verified=True, reason="pending intent 1")
    monkeypatch.undo()
    _fail_on(monkeypatch, ks, phase=("NOT_APPLIED", "APPLIED", "UNRESOLVED"))
    with pytest.raises(KillSwitchRefused, match="resume is refused"):
        ks.resume(operator="owner", verified=True, reason="go")
    result = ks.halt(operator="owner", verified=True, reason="emergency")  # sequence 2, published anyway
    assert result.applied and result.history.startswith("incomplete") and ks.read().state.sequence == 2
    monkeypatch.undo()
    ks.halt(operator="owner", verified=True, reason="later")
    one = [p for s, p in phases(ks) if s == 1]
    assert one == ["INTENT", "UNRESOLVED"]  # the later flag 2 never proves intent 1 NOT_APPLIED


@pytest.mark.unit
def test_an_unreadable_flag_leaves_an_intent_unresolved_and_refuses_that_resume(ks, monkeypatch):
    _fail_on(monkeypatch, ks, publish=True, error=KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        ks.halt(operator="owner", verified=True, reason="pending")
    monkeypatch.undo()
    ks.flag_path.parent.mkdir(parents=True, exist_ok=True)
    ks.flag_path.write_text("garbage", encoding="utf-8")
    with pytest.raises(KillSwitchRefused, match="UNRESOLVED"):
        ks.resume(operator="owner", verified=True, reason="go")
    assert (1, "UNRESOLVED") in phases(ks)


@pytest.mark.unit
def test_a_truncated_journal_tail_is_ignored_and_the_next_line_starts_fresh(ks):
    ks.halt(operator="owner", verified=True, reason="x")
    with open(ks.journal_path, "ab") as handle:
        handle.write(b'{"seq": 9, "pha')  # a crash mid-append
    ks.halt(operator="owner", verified=True, reason="y")
    assert phases(ks) == [(1, "INTENT"), (1, "APPLIED"), (2, "INTENT"), (2, "APPLIED")]
    assert any("truncated" in w or "malformed" in w for w in ks.warnings)


@pytest.mark.unit
def test_sync_audit_is_idempotent_and_audit_events_are_deterministic(ks):
    ks.halt(operator="owner", verified=True, reason="x")
    ks.resume(operator="owner", verified=True, reason="y")
    seen = []
    ks.sync_audit(lambda seq, phase, data: seen.append(admin_module.audit_event(seq, phase, data)))
    again = []
    ks.sync_audit(lambda seq, phase, data: again.append(admin_module.audit_event(seq, phase, data)))
    assert [e.event_id for e in seen] == [e.event_id for e in again]
    assert [e.action for e in seen] == ["killswitch.halt", "killswitch.resume"]
    assert seen[0].at == NOW and NOW - timedelta(0) == seen[1].at


@pytest.mark.unit
def test_a_halt_never_calls_the_history_complete_while_earlier_changes_are_unresolved(ks, monkeypatch):
    """N3 (Codex M4 re-review): after `[INTENT 1, UNRESOLVED 1, INTENT 2, APPLIED 2]` the halt's caption said
    "complete". It describes the whole history, so it says what remains unresolved."""
    _fail_on(monkeypatch, ks, publish=True, error=KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        ks.halt(operator="owner", verified=True, reason="crashes before publishing")
    monkeypatch.undo()
    result = ks.halt(operator="owner", verified=True, reason="halt again")
    assert phases(ks) == [(1, "INTENT"), (1, "UNRESOLVED"), (2, "INTENT"), (2, "APPLIED")]
    assert result.applied and result.history.startswith("incomplete") and "UNRESOLVED" in result.history
