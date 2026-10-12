"""Import only verified corporate actions; the store owns revision assignment."""

import uuid
from dataclasses import dataclass
from importlib.metadata import version
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from investment_engine.clock import Clock
from investment_engine.market.availability import check_utc
from investment_engine.market.corporate_actions import ActionType, AmountBasis, ex_date_start
from investment_engine.market.importers.yahoo_semantics import (
    YAHOO_VERIFICATION,
    FieldBlocked,
    FieldKey,
    Transformation,
    VerificationRecord,
    check_cited_splits,
    check_same_split_history,
    factor_from_history,
    reconstruct_price,
    series_values,
    transformation_for,
)
from investment_engine.money import Money
from investment_engine.storage.sqlite import SqliteInstrumentRepository, SqliteSymbolResolver

if TYPE_CHECKING:
    from investment_engine.market.store.writer import MarketDataWriter, WriteResult


@dataclass(frozen=True)
class ActionImportReport:
    write: "WriteResult"
    skipped_before_verified_from: int


def fetch_full_splits(symbol):
    import yfinance as yf
    return yf.Ticker(symbol).splits


def fetch_full_dividends(symbol):
    import yfinance as yf
    return yf.Ticker(symbol).dividends


def import_actions(instrument_id: str, *, clock: Clock, resolver: SqliteSymbolResolver,
                   instruments: SqliteInstrumentRepository, writer: "MarketDataWriter",
                   fetch_split_history=fetch_full_splits, fetch_dividends=fetch_full_dividends,
                   verification: VerificationRecord = YAHOO_VERIFICATION) -> ActionImportReport:
    if instrument_id != verification.instrument_id:
        raise ValueError("instrument has no matching verification record")
    source_version = version("yfinance")
    transformation_for(FieldKey.SPLIT_RATIO, source_version, verification)
    dividend_transform = transformation_for(FieldKey.DIVIDEND_AMOUNT, source_version, verification)
    instrument = instruments.get(instrument_id)
    exchange_date = check_utc(clock.now(), "clock.now()").astimezone(ZoneInfo(instrument.timezone)).date()
    symbol = resolver.symbol_for(instrument_id, "yfinance", exchange_date)

    before = series_values(fetch_split_history(symbol), instrument.timezone, verified_from=verification.verified_from)
    dividends = series_values(fetch_dividends(symbol), instrument.timezone, verified_from=verification.verified_from)
    received_at = check_utc(clock.now(), "received_at")
    after = series_values(fetch_split_history(symbol), instrument.timezone, verified_from=verification.verified_from)
    check_same_split_history(before, after, verification)
    splits = check_cited_splits(before, verification)
    if not dividends:
        raise ValueError("empty dividend response for the verified dividend-paying instrument")
    processed_at = check_utc(clock.now(), "processed_at")

    # Importing the module is possible without the optional storage extra.
    from investment_engine.market.store.writer import ActionObservation

    observations = []
    context = {"source": "yfinance", "instrument_id": instrument_id, "currency": instrument.currency,
               "exchange_timezone": instrument.timezone, "source_version": source_version,
               "received_at": received_at, "processed_at": processed_at, "new_symbol": None}
    for d, ratio in splits:
        observations.append(ActionObservation(**context, action_type=ActionType.SPLIT, ex_date=d, ratio=ratio,
                                               amount=None, amount_basis=None,
                                               backfill_available_from=ex_date_start(d, instrument.timezone)))
    skipped = sum(d < verification.verified_from for d, _ in before)
    for d, value in dividends:
        if d < verification.verified_from:
            skipped += 1
            continue
        if value <= 0:
            raise ValueError("dividend amount must be positive")
        factor = factor_from_history(splits, d, received_at.astimezone(ZoneInfo(instrument.timezone)).date(),
                                     verification)
        if dividend_transform is Transformation.IDENTITY_IF_NO_LATER_SPLIT and factor != 1:
            raise FieldBlocked("DIVIDEND_AMOUNT identity exception requires F == 1")
        multiplier = factor if dividend_transform is Transformation.SPLIT_RECONSTRUCTION else 1
        basis = {
            Transformation.IDENTITY: AmountBasis.AS_REPORTED,
            Transformation.SPLIT_RECONSTRUCTION: AmountBasis.RECONSTRUCTED_FROM_SPLIT_ADJUSTED,
            Transformation.IDENTITY_IF_NO_LATER_SPLIT: AmountBasis.NO_LATER_SPLIT,
        }[dividend_transform]
        observations.append(ActionObservation(**context, action_type=ActionType.DIVIDEND, ex_date=d, ratio=None,
                                               amount=Money(reconstruct_price(value, multiplier), instrument.currency),
                                               amount_basis=basis,
                                               backfill_available_from=ex_date_start(d, instrument.timezone)))
    result = writer.write_corporate_actions(observations, uuid.uuid4().hex)
    return ActionImportReport(result, skipped)
