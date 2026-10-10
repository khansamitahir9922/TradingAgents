"""Explicit time (architecture Law 5; docs/tasks/M1-01.md).

Business code takes the time from an injected Clock: LiveClock in live use,
ReplayClock when replaying history. Every datetime a contract carries is
timezone-aware UTC, so no result depends on the machine's time zone.
"""

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from investment_engine.clock import LiveClock, ReplayClock, ensure_utc

NEW_YORK = ZoneInfo("America/New_York")


@pytest.mark.unit
def test_live_clock_returns_aware_utc():
    now = LiveClock().now()
    assert now.tzinfo is UTC


@pytest.mark.unit
def test_replay_clock_starts_at_its_start():
    start = datetime(2024, 6, 3, 20, 0, tzinfo=UTC)
    assert ReplayClock(start).now() == start


@pytest.mark.unit
def test_replay_clock_stores_its_start_in_utc():
    # 16:00 in New York on 3 June 2024 (EDT, UTC-4) is 20:00 UTC.
    clock = ReplayClock(datetime(2024, 6, 3, 16, 0, tzinfo=NEW_YORK))
    assert clock.now() == datetime(2024, 6, 3, 20, 0, tzinfo=UTC)
    assert clock.now().tzinfo is UTC


@pytest.mark.unit
def test_replay_clock_rejects_a_naive_start():
    with pytest.raises(ValueError):
        ReplayClock(datetime(2024, 6, 3, 20, 0))


@pytest.mark.unit
def test_replay_clock_advances_to_a_later_time():
    clock = ReplayClock(datetime(2024, 6, 3, 20, 0, tzinfo=UTC))
    later = datetime(2024, 6, 4, 20, 0, tzinfo=UTC)
    clock.advance_to(later)
    assert clock.now() == later


@pytest.mark.unit
def test_replay_clock_may_advance_to_the_same_time():
    start = datetime(2024, 6, 3, 20, 0, tzinfo=UTC)
    clock = ReplayClock(start)
    clock.advance_to(start)
    assert clock.now() == start


@pytest.mark.unit
def test_replay_clock_never_goes_backwards():
    clock = ReplayClock(datetime(2024, 6, 3, 20, 0, tzinfo=UTC))
    with pytest.raises(ValueError):
        clock.advance_to(datetime(2024, 6, 3, 19, 59, 59, tzinfo=UTC))
    assert clock.now() == datetime(2024, 6, 3, 20, 0, tzinfo=UTC)


@pytest.mark.unit
def test_replay_clock_rejects_a_naive_target():
    clock = ReplayClock(datetime(2024, 6, 3, 20, 0, tzinfo=UTC))
    with pytest.raises(ValueError):
        clock.advance_to(datetime(2024, 6, 4, 20, 0))


@pytest.mark.unit
def test_replay_clock_advances_by_a_duration():
    clock = ReplayClock(datetime(2024, 6, 3, 20, 0, tzinfo=UTC))
    clock.advance_by(timedelta(hours=1))
    clock.advance_by(timedelta(0))
    assert clock.now() == datetime(2024, 6, 3, 21, 0, tzinfo=UTC)


@pytest.mark.unit
def test_replay_clock_rejects_a_negative_duration():
    clock = ReplayClock(datetime(2024, 6, 3, 20, 0, tzinfo=UTC))
    with pytest.raises(ValueError):
        clock.advance_by(timedelta(seconds=-1))
    assert clock.now() == datetime(2024, 6, 3, 20, 0, tzinfo=UTC)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("local", "expected_utc"),
    [
        # Before the spring change on 10 March 2024: EST, UTC-5.
        (datetime(2024, 3, 10, 1, 30, tzinfo=NEW_YORK), datetime(2024, 3, 10, 6, 30, tzinfo=UTC)),
        # After it: EDT, UTC-4.
        (datetime(2024, 3, 10, 3, 30, tzinfo=NEW_YORK), datetime(2024, 3, 10, 7, 30, tzinfo=UTC)),
        # The repeated hour on 3 November 2024: first EDT, then EST.
        (datetime(2024, 11, 3, 1, 30, fold=0, tzinfo=NEW_YORK), datetime(2024, 11, 3, 5, 30, tzinfo=UTC)),
        (datetime(2024, 11, 3, 1, 30, fold=1, tzinfo=NEW_YORK), datetime(2024, 11, 3, 6, 30, tzinfo=UTC)),
        # A fixed offset, and UTC itself.
        (datetime(2024, 6, 3, 22, 0, tzinfo=timezone(timedelta(hours=2))), datetime(2024, 6, 3, 20, 0, tzinfo=UTC)),
        (datetime(2024, 6, 3, 20, 0, tzinfo=UTC), datetime(2024, 6, 3, 20, 0, tzinfo=UTC)),
    ],
)
def test_ensure_utc_converts_aware_times_across_dst_changes(local, expected_utc):
    converted = ensure_utc(local)
    assert converted == expected_utc
    assert converted.tzinfo is UTC
    assert (converted.year, converted.month, converted.day, converted.hour, converted.minute) == (
        expected_utc.year, expected_utc.month, expected_utc.day, expected_utc.hour, expected_utc.minute,
    )


@pytest.mark.unit
def test_ensure_utc_rejects_a_naive_time():
    with pytest.raises(ValueError):
        ensure_utc(datetime(2024, 6, 3, 20, 0))
