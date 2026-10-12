"""Trading calendar, part 2: cited holidays, early closes and special closures (docs/tasks/M1-07.md).

Every closure in investment_engine/market/calendar/data/us_equities.json cites
an official NYSE Group source. The spot checks below name the source each
expected value was taken from.
"""

import json
from datetime import UTC, date, datetime, time, timedelta
from importlib.resources import files

import pytest

from investment_engine.market.calendar import CalendarRangeError, UsEquitiesCalendar
from investment_engine.market.calendar.us_equities import load_us_equities_calendar

DATA = json.loads(
    files("investment_engine.market.calendar").joinpath("data", "us_equities.json").read_text(encoding="utf-8")
)
YEARS = range(2019, 2027)


@pytest.fixture(scope="module")
def cal() -> UsEquitiesCalendar:
    return load_us_equities_calendar()


# ---------------------------------------------------------------- the loaded calendar


@pytest.mark.unit
def test_the_loaded_calendar_covers_2019_to_2026(cal):
    assert (cal.covered_from, cal.covered_to) == (date(2019, 1, 1), date(2026, 12, 31))
    with pytest.raises(CalendarRangeError):
        cal.is_session(date(2018, 12, 31))
    with pytest.raises(CalendarRangeError):
        cal.is_session(date(2027, 1, 4))


@pytest.mark.unit
def test_every_listed_closure_is_not_a_session(cal):
    for entry in DATA["closures"]:
        assert not cal.is_session(date.fromisoformat(entry["date"])), entry


@pytest.mark.unit
def test_every_listed_early_close_ends_at_its_stated_time(cal):
    for entry in DATA["early_closes"]:
        day = date.fromisoformat(entry["date"])
        session = cal.session(day)
        local_close = datetime.combine(day, time.fromisoformat(entry["close"]), tzinfo=cal._zone)
        assert session.is_half_day and session.close == local_close.astimezone(UTC), entry


# ---------------------------------------------------------------- cited spot checks
# Each case: (date, expectation, source ID the expectation was read from).


def utc(*parts) -> datetime:
    return datetime(*parts, tzinfo=UTC)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("day", "source"),
    [
        (date(2024, 3, 29), "nyse-2022-2024"),   # Good Friday
        (date(2019, 4, 19), "nyse-2019-2021"),   # Good Friday
        (date(2022, 6, 20), "nyse-2022-2024"),   # Juneteenth (observed), its first year
        (date(2024, 6, 19), "nyse-2022-2024"),   # Juneteenth
        (date(2024, 11, 28), "nyse-2022-2024"),  # Thanksgiving
        (date(2020, 7, 3), "nyse-2019-2021"),    # Independence Day observed on a Friday
        (date(2021, 7, 5), "nyse-2019-2021"),    # Independence Day observed on a Monday
        (date(2026, 7, 3), "nyse-2025-2027"),    # Independence Day observed on a Friday
        (date(2021, 12, 24), "nyse-2019-2021"),  # Christmas observed on a Friday: a full closure
        (date(2025, 1, 9), "nyse-carter-2025"),  # special closure: national day of mourning
    ],
)
def test_cited_closures(cal, day, source):
    assert source in {s["id"] for s in DATA["sources"]}
    assert not cal.is_session(day)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("day", "close_utc", "source"),
    [
        (date(2024, 11, 29), utc(2024, 11, 29, 18, 0), "nyse-2022-2024"),  # day after Thanksgiving, 13:00 EST
        (date(2024, 12, 24), utc(2024, 12, 24, 18, 0), "nyse-2022-2024"),  # Christmas Eve on a weekday
        (date(2019, 7, 3), utc(2019, 7, 3, 17, 0), "nyse-2019-2021"),      # 13:00 EDT
        (date(2025, 12, 24), utc(2025, 12, 24, 18, 0), "nyse-2025-2027"),
    ],
)
def test_cited_early_closes(cal, day, close_utc, source):
    assert source in {s["id"] for s in DATA["sources"]}
    session = cal.session(day)
    assert session.is_half_day and session.close == close_utc


@pytest.mark.unit
@pytest.mark.parametrize(
    ("day", "why", "source"),
    [
        # New Year's Day 2022 fell on a Saturday and wasn't observed, so Friday was a normal session.
        (date(2021, 12, 31), "no observed New Year's holiday", "nyse-2022-2024"),
        # Juneteenth only became an NYSE holiday in 2022.
        (date(2021, 6, 18), "no Juneteenth closure in 2021", "nyse-2021-2023"),
        # Christmas 2021 was observed on Friday the 24th; Thursday the 23rd wasn't an early close.
        (date(2021, 12, 23), "regular hours before an observed holiday", "nyse-2019-2021"),
    ],
)
def test_cited_regular_sessions(cal, day, why, source):
    assert source in {s["id"] for s in DATA["sources"]}
    session = cal.session(day)
    assert not session.is_half_day, why
    assert session.close == datetime.combine(day, time(16, 0), tzinfo=cal._zone).astimezone(UTC)


@pytest.mark.unit
def test_the_special_closure_shifts_next_and_previous(cal):
    assert cal.next_session(date(2025, 1, 8)).date == date(2025, 1, 10)
    assert cal.previous_session(date(2025, 1, 10)).date == date(2025, 1, 8)


# ---------------------------------------------------------------- the data file itself


@pytest.mark.unit
def test_the_data_file_is_internally_consistent():
    covered_from = date.fromisoformat(DATA["covered_from"])
    covered_to = date.fromisoformat(DATA["covered_to"])
    source_ids = [s["id"] for s in DATA["sources"]]
    assert len(source_ids) == len(set(source_ids))
    for s in DATA["sources"]:
        assert s["url"].startswith("https://") and s["title"] and date.fromisoformat(s["retrieved"])

    dates = [e["date"] for e in DATA["closures"]] + [e["date"] for e in DATA["early_closes"]]
    assert len(dates) == len(set(dates)), "a date is listed twice"
    for entry in DATA["closures"] + DATA["early_closes"]:
        day = date.fromisoformat(entry["date"])
        assert covered_from <= day <= covered_to, entry
        assert day.weekday() < 5, f"{entry} falls on a weekend"
        assert entry["reason"], entry
        assert entry["source"] in source_ids, entry
    for entry in DATA["early_closes"]:
        assert time.fromisoformat(entry["close"]) == time(13, 0), entry
    assert DATA["timezone"] == "America/New_York"
    assert DATA["regular"] == {"open": "09:30", "close": "16:00"}


@pytest.mark.unit
@pytest.mark.parametrize("year", YEARS)
def test_every_covered_year_has_its_standard_closures(year):
    # A completeness check: every year has nine or ten scheduled holidays
    # (ten from 2022, with Juneteenth), less any that fell on a Saturday and
    # weren't observed, plus any special closure, and an early close the day
    # after Thanksgiving.
    closures = [e for e in DATA["closures"] if e["date"].startswith(str(year))]
    early = [e for e in DATA["early_closes"] if e["date"].startswith(str(year))]
    assert 8 <= len(closures) <= 11, (year, len(closures))
    assert any("Thanksgiving" in e["reason"] for e in closures)
    assert any("Day after Thanksgiving" in e["reason"] for e in early)
    thanksgiving = next(date.fromisoformat(e["date"]) for e in closures if e["reason"] == "Thanksgiving Day")
    assert thanksgiving.weekday() == 3 and 22 <= thanksgiving.day <= 28   # the fourth Thursday
    assert date.fromisoformat(next(e["date"] for e in early if "Thanksgiving" in e["reason"])) == (
        thanksgiving + timedelta(days=1)
    )


# Expected sessions per year, worked out by hand from the cited schedules
# (Codex review of batch 2): weekdays in the year less the weekday closures
# the sources list. Saturday holidays observed on Friday count as weekday
# closures; New Year's Day 2022 (a Saturday) wasn't observed, per NYSE rule.
#   year  weekdays  closures  sessions
#   2019    261        9        252
#   2020    262        9        253
#   2021    261        9        252   (Juneteenth not yet a market holiday)
#   2022    260        9        251
#   2023    260       10        250
#   2024    262       10        252
#   2025    261       11        250   (includes the 2025-01-09 national day of mourning)
#   2026    261       10        251
EXPECTED_SESSIONS = {2019: 252, 2020: 253, 2021: 252, 2022: 251, 2023: 250, 2024: 252, 2025: 250, 2026: 251}


@pytest.mark.unit
def test_sessions_per_year_match_the_cited_schedules(cal):
    counts = {
        year: len(cal.sessions_between(date(year, 1, 1), date(year, 12, 31))) for year in YEARS
    }
    assert counts == EXPECTED_SESSIONS


@pytest.mark.unit
@pytest.mark.parametrize("year", YEARS)
def test_the_expected_counts_are_weekdays_less_weekday_closures(year):
    # Ties the hand-worked table to the data: a missing or extra closure
    # changes the count and fails one of these tests.
    days = (date(year, 1, 1) + timedelta(days=n) for n in range(366))
    weekdays = sum(1 for day in days if day.year == year and day.weekday() < 5)
    closures = [e for e in DATA["closures"] if e["date"].startswith(str(year))]
    assert all(date.fromisoformat(e["date"]).weekday() < 5 for e in closures)
    assert weekdays - len(closures) == EXPECTED_SESSIONS[year]
