"""When a market-data record may be seen, and who supplied it (docs/tasks/M1-08.md).

Every stored revision of a candle or corporate action keeps two kinds of time
apart (roadmap §4.1):
- observation, `received_at`: when this system actually received it;
- availability, `available_from` with its basis: the earliest replay time at
  which it may be seen.

A record first seen in a historical download is BACKFILL_ASSUMED: its
availability is an assumption, labelled as one. Any later revision is
OBSERVED, available only from its own observation time, and never backdated.
The checks here are shared by every market-data contract.
"""

import re
from datetime import datetime, timedelta
from enum import StrEnum

PROVIDER_ID_PATTERN = r"^[a-z][a-z0-9_]*$"  # e.g. "yfinance"; same values as SymbolMapping.provider
# The same rule as Instrument (M1-03); tests/engine/test_availability.py keeps the two in step.
INSTRUMENT_ID_PATTERN = r"^(EQ|ETF)_[A-Z]{2}_[A-Z0-9]+(_[0-9]+)?$"

_PROVIDER = re.compile(PROVIDER_ID_PATTERN)
_INSTRUMENT_ID = re.compile(INSTRUMENT_ID_PATTERN)


class AvailabilityBasis(StrEnum):
    OBSERVED = "OBSERVED"  # available_from == received_at: we saw it at that time
    BACKFILL_ASSUMED = "BACKFILL_ASSUMED"  # first seen in a historical download; an assumption


def check_utc(value: object, what: str) -> datetime:
    """A timezone-aware datetime with a zero UTC offset; anything else is refused, not converted."""
    if not isinstance(value, datetime):
        raise TypeError(f"{what} must be a datetime, not {type(value).__name__}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{what} must be timezone-aware UTC, not naive")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{what} must be in UTC, not offset {value.utcoffset()}")
    return value


def check_provider(source: object) -> str:
    if not isinstance(source, str) or not _PROVIDER.fullmatch(source):
        raise ValueError(f"source must be a provider id like 'yfinance', not {source!r}")
    return source


def check_instrument_id(instrument_id: object) -> str:
    """A well-formed instrument ID. The store builds folder paths from it, so nothing else is accepted."""
    if not isinstance(instrument_id, str) or not _INSTRUMENT_ID.fullmatch(instrument_id):
        raise ValueError(f"instrument_id must look like EQ_US_NVDA, not {instrument_id!r}")
    return instrument_id


def check_name(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{what} must be a string, not {type(value).__name__}")
    if not value or value != value.strip():
        raise ValueError(f"{what} must be non-empty without surrounding spaces, not {value!r}")
    return value


def check_revision(revision: object) -> int:
    if not isinstance(revision, int) or isinstance(revision, bool):
        raise TypeError(f"revision must be an int, not {type(revision).__name__}")
    if revision < 1:
        raise ValueError(f"revision must be at least 1, not {revision}")
    return revision


def check_availability(
    *,
    revision: int,
    basis: AvailabilityBasis,
    event_time: datetime,
    received_at: datetime,
    available_from: datetime,
) -> None:
    """The availability rules shared by all market-data records (M1-08 rules 4 – 7)."""
    if available_from < event_time:
        raise ValueError(f"available_from {available_from} is before the event at {event_time}")
    if basis is AvailabilityBasis.OBSERVED and available_from != received_at:
        raise ValueError("an OBSERVED record is available exactly when received")
    if revision >= 2 and basis is not AvailabilityBasis.OBSERVED:
        raise ValueError(f"revision {revision} must be OBSERVED: a correction is never backdated")
    if basis is AvailabilityBasis.BACKFILL_ASSUMED and revision != 1:
        raise ValueError("BACKFILL_ASSUMED applies only to revision 1")
