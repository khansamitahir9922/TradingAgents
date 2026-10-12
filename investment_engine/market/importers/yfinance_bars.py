"""Verified daily Yahoo research bars, written as raw observations (M1-13).

Hourly ingestion remains blocked pending independent evidence. No bar-response
action column is ever used for reconstruction; later splits outside the
requested window come from bracketed full-history requests and the store.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from importlib.metadata import version
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from investment_engine.clock import Clock
from investment_engine.market.availability import check_utc
from investment_engine.market.calendar.base import TradingCalendar
from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.importers.yahoo_semantics import (
    YAHOO_VERIFICATION,
    FieldBlocked,
    FieldKey,
    OutsideVerifiedRange,
    SplitHistoryMismatch,
    Transformation,
    VerificationRecord,
    check_cited_splits,
    check_same_split_history,
    decimal_value,
    factor_from_history,
    plain_date,
    reconstruct_price,
    reconstruct_volume,
    series_values,
    transformation_for,
)
from investment_engine.market.importers.yfinance_actions import fetch_full_splits
from investment_engine.storage.sqlite import SqliteInstrumentRepository, SqliteSymbolResolver

if TYPE_CHECKING:
    from investment_engine.market.store.reader import MarketDataReader
    from investment_engine.market.store.writer import MarketDataWriter, WriteResult


@dataclass(frozen=True)
class BarImportReport:
    write: "WriteResult"
    dropped_forming: int
    rejected: list[tuple[datetime, str]]
    covered: tuple[datetime, datetime] | None
    split_history: tuple[tuple[date, Decimal], ...]
    max_split_factor_applied: Decimal


def fetch_daily_bars(symbol, **kwargs):
    import yfinance as yf
    result = yf.Ticker(symbol).history(**kwargs)
    if result.empty:
        raise ValueError("Yahoo returned no bars; import cannot establish requested coverage")
    return result


def _requests(resolver, instrument_id, start, end):
    """Resolve every date before fetching; compress adjacent mappings into requests.

    `end` is exclusive: no lookup on the first excluded date is required.
    A gap raises instead of guessing that a ticker still identifies the asset.
    """
    requests = []
    for offset in range((end - start).days):
        d = start + timedelta(days=offset)
        symbol = resolver.symbol_for(instrument_id, "yfinance", d)
        if requests and requests[-1][0] == symbol:
            requests[-1] = (symbol, requests[-1][1], d + timedelta(days=1))
        else:
            requests.append((symbol, d, d + timedelta(days=1)))
    return requests


def import_bars(instrument_id: str, timeframe: Timeframe, start: date, end: date, *,
                clock: Clock, resolver: SqliteSymbolResolver, instruments: SqliteInstrumentRepository,
                calendar: TradingCalendar, reader: "MarketDataReader", writer: "MarketDataWriter",
                fetch_bars=fetch_daily_bars, fetch_split_history=fetch_full_splits,
                backfill_latency: timedelta = timedelta(0),
                verification: VerificationRecord = YAHOO_VERIFICATION) -> BarImportReport:
    plain_date(start, "start")
    plain_date(end, "end")
    if end <= start:
        raise ValueError("end must be after start (exclusive)")
    if start < verification.verified_from:
        raise OutsideVerifiedRange(f"start precedes verified_from {verification.verified_from}")
    if not isinstance(backfill_latency, timedelta) or backfill_latency < timedelta(0):
        raise ValueError("backfill latency must be a nonnegative timedelta")
    if instrument_id != verification.instrument_id:
        raise ValueError("instrument has no matching verification record")
    timeframe = Timeframe(timeframe)
    source_version = version("yfinance")
    price_key, volume_key = ((FieldKey.D1_PRICE, FieldKey.D1_VOLUME) if timeframe is Timeframe.D1
                             else (FieldKey.H1_PRICE, FieldKey.H1_VOLUME))
    price_transform = transformation_for(price_key, source_version, verification)
    volume_transform = transformation_for(volume_key, source_version, verification)
    if timeframe is not Timeframe.D1:
        raise FieldBlocked("hourly implementation remains paused pending independent verification")
    instrument = instruments.get(instrument_id)
    if instrument.timezone != calendar.timezone:
        raise ValueError("calendar timezone must match instrument context")
    # Refuse dates the calendar cannot establish, before network or storage writes.
    calendar.sessions_between(start, end - timedelta(days=1))
    requests = [r for r in _requests(resolver, instrument_id, start, end)
                if calendar.sessions_between(r[1], r[2] - timedelta(days=1))]
    stored = reader.actions_latest("yfinance", instrument_id, verification.verified_from, date.max, {ActionType.SPLIT})
    stored_splits = tuple(sorted((a.ex_date, a.ratio) for a in stored))
    downloaded = []
    history_used = None
    for symbol, request_start, request_end in requests:
        before = series_values(fetch_split_history(symbol), instrument.timezone, verified_from=verification.verified_from)
        data = fetch_bars(symbol, start=request_start, end=request_end, interval="1d", auto_adjust=False,
                          actions=False, repair=False, back_adjust=False, prepost=False)
        received_at = check_utc(clock.now(), "received_at")
        after = series_values(fetch_split_history(symbol), instrument.timezone, verified_from=verification.verified_from)
        check_same_split_history(before, after, verification)
        history = check_cited_splits(before, verification)
        if history != stored_splits:
            raise SplitHistoryMismatch("stored splits differ: run the action import first")
        if history_used is not None and history != history_used:
            raise SplitHistoryMismatch("split history changed mid-run across symbol requests")
        history_used = history
        downloaded.append((data, received_at, request_start, request_end))

    from investment_engine.market.store.writer import CandleObservation

    observations, rejected, seen = [], [], set()
    dropped = 0
    max_factor = Decimal("1")
    processed_at = check_utc(clock.now(), "processed_at")
    zone = ZoneInfo(instrument.timezone)
    required = ("Open", "High", "Low", "Close", "Volume")
    for data, received_at, request_start, request_end in downloaded:
        if not set(required) <= set(data.columns) or not data.columns.is_unique:
            raise ValueError("bar response needs unique Open, High, Low, Close, Volume columns")
        if data.empty:
            raise ValueError("empty bar response; requested coverage cannot be established")
        for timestamp, *values in data.loc[:, list(required)].itertuples(index=True, name=None):
            if not isinstance(timestamp, datetime) or timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("vendor bar timestamps must be timezone-aware")
            # pandas timestamps remain aware; conversion below is explicit, never a guess.
            exchange_date = timestamp.astimezone(zone).date()
            timestamp_utc = timestamp.astimezone(ZoneInfo("UTC"))
            if not request_start <= exchange_date < request_end:
                rejected.append((timestamp_utc, "outside requested end-exclusive window"))
                continue
            if not calendar.is_session(exchange_date):
                rejected.append((timestamp_utc, "non-session date"))
                continue
            session = calendar.session(exchange_date)
            if session.close > check_utc(clock.now(), "clock.now()"):
                dropped += 1
                continue
            if session.open in seen:
                raise ValueError("duplicate daily bar identity")
            seen.add(session.open)
            factor = factor_from_history(history_used, exchange_date, received_at.astimezone(zone).date())
            if any(t is Transformation.IDENTITY_IF_NO_LATER_SPLIT and factor != 1 for t in (price_transform, volume_transform)):
                rejected.append((timestamp_utc, "identity exception requires F == 1"))
                continue
            numbers = [decimal_value(v) for v in values]
            if numbers[-1] < 0:
                raise ValueError("vendor volume must be nonnegative")
            prices = [reconstruct_price(v, factor if price_transform is Transformation.SPLIT_RECONSTRUCTION else 1)
                      for v in numbers[:4]]
            volume = reconstruct_volume(numbers[4], factor if volume_transform is Transformation.SPLIT_RECONSTRUCTION else 1)
            price_basis = {
                Transformation.IDENTITY: PriceBasis.RAW_AS_REPORTED,
                Transformation.SPLIT_RECONSTRUCTION: PriceBasis.RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED,
                Transformation.IDENTITY_IF_NO_LATER_SPLIT: PriceBasis.RAW_NO_LATER_SPLIT,
            }[price_transform]
            volume_basis = {
                Transformation.IDENTITY: VolumeBasis.RAW_AS_REPORTED,
                Transformation.SPLIT_RECONSTRUCTION: VolumeBasis.RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED,
                Transformation.IDENTITY_IF_NO_LATER_SPLIT: VolumeBasis.RAW_NO_LATER_SPLIT,
            }[volume_transform]
            observations.append(CandleObservation(
                source="yfinance", instrument_id=instrument_id, timeframe=timeframe,
                start_time=session.open, end_time=session.close, open=prices[0], high=prices[1], low=prices[2],
                close=prices[3], currency=instrument.currency, volume=volume, state=BarState.CLOSED,
                source_version=source_version, price_basis=price_basis, volume_basis=volume_basis,
                event_time=session.close, received_at=received_at, processed_at=processed_at,
                backfill_available_from=session.close + backfill_latency,
            ))
            if price_transform is Transformation.SPLIT_RECONSTRUCTION or volume_transform is Transformation.SPLIT_RECONSTRUCTION:
                max_factor = max(max_factor, factor)
    result = writer.write_candles(observations, uuid.uuid4().hex)
    covered = (min(o.start_time for o in observations), max(o.end_time for o in observations)) if observations else None
    return BarImportReport(result, dropped, rejected, covered, history_used or (), max_factor)
