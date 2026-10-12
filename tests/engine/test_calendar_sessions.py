"""Trading calendar, part 1: regular US equity sessions (Law 6; docs/tasks/M1-06.md).

Sessions are exchange-local wall times (09:30-16:00 America/New_York)
converted to UTC by the time-zone database, so daylight saving needs no
special cases. No result depends on the machine's own time zone.
"""

from datetime import UTC, date, datetime, time

import pytest

from investment_engine.market.calendar import (
    CalendarRangeError,
    Session,
    TradingCalendar,
    UsEquitiesCalendar,
)

COVER = {"covered_from": date(2024, 1, 1), "covered_to": date(2024, 12, 31)}


def calendar(**extra) -> UsEquitiesCalendar:
    return UsEquitiesCalendar(**COVER, **extra)


def utc(*parts) -> datetime:
    return datetime(*parts, tzinfo=UTC)


@pytest.mark.unit
def test_the_us_calendar_satisfies_the_port():
    assert isinstance(calendar(), TradingCalendar)
    assert calendar().timezone == "America/New_York"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("day", "opens", "closes"),
    [
        # Before the spring change on 10 March 2024: EST, UTC-5.
        (date(2024, 3, 8), utc(2024, 3, 8, 14, 30), utc(2024, 3, 8, 21, 0)),
        # After it: EDT, UTC-4.
        (date(2024, 3, 11), utc(2024, 3, 11, 13, 30), utc(2024, 3, 11, 20, 0)),
        # The Friday before the autumn change on 3 November: still EDT.
        (date(2024, 11, 1), utc(2024, 11, 1, 13, 30), utc(2024, 11, 1, 20, 0)),
        # After it: EST again.
        (date(2024, 11, 4), utc(2024, 11, 4, 14, 30), utc(2024, 11, 4, 21, 0)),
    ],
)
def test_sessions_follow_daylight_saving(day, opens, closes):
    session = calendar().session(day)
    assert session == Session(date=day, open=opens, close=closes, is_half_day=False)
    assert session.open.tzinfo is UTC and session.close.tzinfo is UTC


@pytest.mark.unit
@pytest.mark.parametrize("day", [date(2024, 3, 9), date(2024, 3, 10)])
def test_weekends_are_never_sessions(day):
    cal = calendar()
    assert not cal.is_session(day)
    with pytest.raises(ValueError):
        cal.session(day)


@pytest.mark.unit
def test_sessions_between_is_inclusive_and_skips_the_weekend():
    days = [s.date for s in calendar().sessions_between(date(2024, 3, 7), date(2024, 3, 12))]
    assert days == [date(2024, 3, 7), date(2024, 3, 8), date(2024, 3, 11), date(2024, 3, 12)]


@pytest.mark.unit
def test_sessions_between_a_weekend_only_is_empty():
    assert calendar().sessions_between(date(2024, 3, 9), date(2024, 3, 10)) == []


@pytest.mark.unit
def test_sessions_between_refuses_a_reversed_range():
    with pytest.raises(ValueError):
        calendar().sessions_between(date(2024, 3, 12), date(2024, 3, 7))


@pytest.mark.unit
def test_next_and_previous_session_cross_the_weekend():
    cal = calendar()
    assert cal.next_session(date(2024, 3, 8)).date == date(2024, 3, 11)       # Friday -> Monday
    assert cal.next_session(date(2024, 3, 9)).date == date(2024, 3, 11)       # Saturday -> Monday
    assert cal.previous_session(date(2024, 3, 11)).date == date(2024, 3, 8)   # Monday -> Friday
    assert cal.previous_session(date(2024, 3, 10)).date == date(2024, 3, 8)   # Sunday -> Friday
    assert cal.next_session(date(2024, 3, 12)).date == date(2024, 3, 13)      # strictly after


@pytest.mark.unit
@pytest.mark.parametrize("day", [date(2023, 12, 31), date(2025, 1, 1)])
def test_dates_outside_coverage_raise(day):
    cal = calendar()
    for call in (cal.is_session, cal.session, cal.next_session, cal.previous_session):
        with pytest.raises(CalendarRangeError):
            call(day)
    with pytest.raises(CalendarRangeError):
        cal.sessions_between(date(2024, 12, 30), date(2025, 1, 2))
    assert issubclass(CalendarRangeError, LookupError)


@pytest.mark.unit
def test_next_and_previous_never_guess_past_coverage():
    cal = calendar(holidays=frozenset({date(2024, 1, 1)}))
    with pytest.raises(CalendarRangeError):
        cal.next_session(date(2024, 12, 31))      # the next session is in 2025, not covered
    with pytest.raises(CalendarRangeError):
        cal.previous_session(date(2024, 1, 2))    # 1 January is closed; the one before is in 2023


@pytest.mark.unit
def test_holidays_and_half_days_supplied_to_the_calendar_are_honoured():
    # Real data and its sources come in M1-07; here the mechanism is tested.
    cal = calendar(
        holidays=frozenset({date(2024, 1, 1), date(2024, 7, 4)}),
        half_days={date(2024, 7, 3): time(13, 0)},
    )
    assert not cal.is_session(date(2024, 7, 4))
    assert cal.next_session(date(2024, 7, 3)).date == date(2024, 7, 5)
    half = cal.session(date(2024, 7, 3))
    assert half.is_half_day and half.close == utc(2024, 7, 3, 17, 0)   # 13:00 EDT
    assert half.open == utc(2024, 7, 3, 13, 30)


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad",
    [
        {"holidays": frozenset({date(2023, 12, 25)})},                    # outside coverage
        {"holidays": frozenset({date(2024, 3, 9)})},                      # a Saturday
        {"half_days": {date(2024, 3, 10): time(13, 0)}},                  # a Sunday
        {"half_days": {date(2024, 7, 3): time(17, 0)}},                   # after the regular close
        {"holidays": frozenset({date(2024, 7, 3)}), "half_days": {date(2024, 7, 3): time(13, 0)}},
    ],
)
def test_inconsistent_closures_are_refused(bad):
    with pytest.raises(ValueError):
        calendar(**bad)


@pytest.mark.unit
def test_coverage_must_be_a_forward_range_of_dates():
    with pytest.raises(ValueError):
        UsEquitiesCalendar(covered_from=date(2024, 12, 31), covered_to=date(2024, 1, 1))
    with pytest.raises(TypeError):
        UsEquitiesCalendar(covered_from=datetime(2024, 1, 1), covered_to=date(2024, 12, 31))


@pytest.mark.unit
def test_queries_take_dates_not_datetimes():
    with pytest.raises(TypeError):
        calendar().is_session(datetime(2024, 3, 8, 12, 0))


@pytest.mark.unit
def test_sessions_are_immutable():
    with pytest.raises(AttributeError):
        calendar().session(date(2024, 3, 8)).is_half_day = True
