"""Parquet schemas and record conversion for the market-data store (docs/tasks/M1-10.md).

Exact decimals on disk, never floats: prices and per-share amounts as
decimal128(18, 4), share volumes as decimal128(20, 0), split ratios as
decimal128(28, 12); times as microsecond UTC timestamps. A value that doesn't
fit its column exactly is refused, not rounded.
"""

from datetime import UTC, datetime

import pyarrow as pa

from investment_engine.market.candles import Candle
from investment_engine.market.corporate_actions import CorporateAction
from investment_engine.money import Money

TIMESTAMP = pa.timestamp("us", tz="UTC")
PRICE = pa.decimal128(18, 4)
SHARES = pa.decimal128(20, 0)
RATIO = pa.decimal128(28, 12)

CANDLE_SCHEMA = pa.schema(
    [
        ("source", pa.string()),
        ("instrument_id", pa.string()),
        ("timeframe", pa.string()),
        ("start_time", TIMESTAMP),
        ("end_time", TIMESTAMP),
        ("open", PRICE),
        ("high", PRICE),
        ("low", PRICE),
        ("close", PRICE),
        ("currency", pa.string()),
        ("volume", SHARES),
        ("state", pa.string()),
        ("source_version", pa.string()),
        ("price_basis", pa.string()),
        ("volume_basis", pa.string()),
        ("import_id", pa.string()),
        ("event_time", TIMESTAMP),
        ("received_at", TIMESTAMP),
        ("processed_at", TIMESTAMP),
        ("revision", pa.int32()),
        ("available_from", TIMESTAMP),
        ("availability_basis", pa.string()),
    ]
)

ACTION_SCHEMA = pa.schema(
    [
        ("source", pa.string()),
        ("instrument_id", pa.string()),
        ("currency", pa.string()),
        ("exchange_timezone", pa.string()),
        ("action_type", pa.string()),
        ("ex_date", pa.date32()),
        ("ratio", RATIO),
        ("amount", PRICE),
        ("amount_currency", pa.string()),
        ("amount_basis", pa.string()),
        ("new_symbol", pa.string()),
        ("source_version", pa.string()),
        ("import_id", pa.string()),
        ("received_at", TIMESTAMP),
        ("processed_at", TIMESTAMP),
        ("revision", pa.int32()),
        ("available_from", TIMESTAMP),
        ("availability_basis", pa.string()),
    ]
)

_CANDLE_TIMES = ("start_time", "end_time", "event_time", "received_at", "processed_at", "available_from")
_ACTION_TIMES = ("received_at", "processed_at", "available_from")


def candle_to_row(candle: Candle) -> dict:
    return {name: getattr(candle, name) for name in CANDLE_SCHEMA.names}


def row_to_candle(row: dict) -> Candle:
    values = dict(row)
    for name in _CANDLE_TIMES:
        values[name] = _utc(values[name])
    return Candle(**values)


def action_to_row(action: CorporateAction) -> dict:
    row = {name: getattr(action, name, None) for name in ACTION_SCHEMA.names}
    row["amount"] = action.amount.amount if action.amount is not None else None
    row["amount_currency"] = action.amount.currency if action.amount is not None else None
    return row


def row_to_action(row: dict) -> CorporateAction:
    values = dict(row)
    amount, currency = values.pop("amount"), values.pop("amount_currency")
    values["amount"] = Money(amount, currency) if amount is not None else None
    for name in _ACTION_TIMES:
        values[name] = _utc(values[name])
    return CorporateAction(**values)


def to_table(rows: list[dict], schema: pa.Schema) -> pa.Table:
    """Build a table, refusing any value that doesn't fit its column exactly."""
    try:
        return pa.Table.from_pylist(rows, schema=schema)
    except (pa.ArrowInvalid, pa.ArrowTypeError) as exc:
        raise ValueError(f"a value doesn't fit the store's exact column types: {exc}") from exc


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)
