"""Point-in-time reads from the market-data store (ADR-009; docs/tasks/M1-11.md).

Every read is for ONE provider (its partition), and names its view:
- latest: the highest revision of each record;
- visible_at(T): the highest revision with available_from <= T, which is
  what a strategy could have known at T (replay uses this);
- recorded_by(T): the highest revision with received_at <= T, which is what
  this system's store held at T (audit).

There's deliberately no default view. Revision histories return every
revision, by record or by availability window. Results are sorted by a total
key that includes the record's full identity plus revision, so the order
never depends on file or row order; action types rank in their declaration
order (SPLIT, DIVIDEND, SYMBOL_CHANGE, DELISTING).

Queries run in DuckDB over the provider's Parquet files and come back as
Arrow tables, converted by the same schema functions the writer uses.
"""

from collections.abc import Collection
from datetime import date, datetime
from pathlib import Path

import duckdb

from investment_engine.market.availability import check_utc
from investment_engine.market.candles import Candle, Timeframe
from investment_engine.market.corporate_actions import ActionType, CorporateAction
from investment_engine.market.store.schema import row_to_action, row_to_candle

_ACTION_RANK = "CASE action_type " + " ".join(
    f"WHEN '{t.value}' THEN {rank}" for rank, t in enumerate(ActionType)
) + " END"


def _plain_date(value: object, what: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{what} must be a date, not {type(value).__name__}")
    return value


class MarketDataReader:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # ---------------------------------------------------------------- candles: one revision per bar

    def candles_latest(self, source: str, instrument_id: str, timeframe: Timeframe,
                       start: datetime, end: datetime) -> list[Candle]:
        return self._candles(source, instrument_id, timeframe, start, end, extra="", one_per_bar=True)

    def candles_visible_at(self, source: str, instrument_id: str, timeframe: Timeframe,
                           start: datetime, end: datetime, at: datetime) -> list[Candle]:
        """Per bar, the highest revision with available_from <= at."""
        return self._candles(source, instrument_id, timeframe, start, end,
                             extra="AND available_from <= ?", params=[check_utc(at, "at")], one_per_bar=True)

    def candles_recorded_by(self, source: str, instrument_id: str, timeframe: Timeframe,
                            start: datetime, end: datetime, at: datetime) -> list[Candle]:
        """Per bar, the highest revision with received_at <= at (audit view)."""
        return self._candles(source, instrument_id, timeframe, start, end,
                             extra="AND received_at <= ?", params=[check_utc(at, "at")], one_per_bar=True)

    # ---------------------------------------------------------------- candles: revision histories

    def candle_revision_history(self, source: str, instrument_id: str, timeframe: Timeframe,
                                start: datetime, end: datetime) -> list[Candle]:
        """Every revision of bars with start_time in [start, end), by (start_time, revision)."""
        return self._candles(source, instrument_id, timeframe, start, end, extra="", one_per_bar=False)

    def candle_revisions_available_between(self, source: str, instrument_id: str, timeframe: Timeframe,
                                           available_start: datetime, available_end: datetime) -> list[Candle]:
        """Every revision, of any bar, with available_from in [available_start, available_end)."""
        files = self._candle_files(source, instrument_id, timeframe)
        if files is None:
            return []
        sql = (
            f"SELECT * FROM {files} WHERE source = ? AND instrument_id = ? AND timeframe = ?"
            " AND available_from >= ? AND available_from < ?"
            " ORDER BY available_from, start_time, revision"
        )
        params = [source, instrument_id, str(Timeframe(timeframe)),
                  check_utc(available_start, "available_start"), check_utc(available_end, "available_end")]
        return [row_to_candle(row) for row in self._query(sql, params)]

    # ---------------------------------------------------------------- corporate actions

    def actions_latest(self, source: str, instrument_id: str, start: date, end: date,
                       types: Collection[ActionType] | None = None) -> list[CorporateAction]:
        return self._actions(source, instrument_id, start, end, types, extra="", one_per_record=True)

    def actions_visible_at(self, source: str, instrument_id: str, start: date, end: date, at: datetime,
                           types: Collection[ActionType] | None = None) -> list[CorporateAction]:
        return self._actions(source, instrument_id, start, end, types, extra="AND available_from <= ?",
                             params=[check_utc(at, "at")], one_per_record=True)

    def actions_recorded_by(self, source: str, instrument_id: str, start: date, end: date, at: datetime,
                            types: Collection[ActionType] | None = None) -> list[CorporateAction]:
        return self._actions(source, instrument_id, start, end, types, extra="AND received_at <= ?",
                             params=[check_utc(at, "at")], one_per_record=True)

    def action_revision_history(self, source: str, instrument_id: str, start: date, end: date,
                                types: Collection[ActionType] | None = None) -> list[CorporateAction]:
        return self._actions(source, instrument_id, start, end, types, extra="", one_per_record=False)

    def action_revisions_available_between(self, source: str, instrument_id: str,
                                           available_start: datetime, available_end: datetime,
                                           types: Collection[ActionType] | None = None) -> list[CorporateAction]:
        files = self._action_files(source, instrument_id)
        if files is None:
            return []
        type_sql, type_params = self._types(types)
        sql = (
            f"SELECT * FROM {files} WHERE source = ? AND instrument_id = ?"
            f" AND available_from >= ? AND available_from < ? {type_sql}"
            f" ORDER BY available_from, ex_date, {_ACTION_RANK}, revision"
        )
        params = [source, instrument_id, check_utc(available_start, "available_start"),
                  check_utc(available_end, "available_end"), *type_params]
        return [row_to_action(row) for row in self._query(sql, params)]

    # ---------------------------------------------------------------- internals

    def _candles(self, source, instrument_id, timeframe, start, end, *, extra, params=(), one_per_bar):
        files = self._candle_files(source, instrument_id, timeframe)
        if files is None:
            return []
        where = (
            "source = ? AND instrument_id = ? AND timeframe = ? AND start_time >= ? AND start_time < ? " + extra
        )
        args = [source, instrument_id, str(Timeframe(timeframe)), check_utc(start, "start"),
                check_utc(end, "end"), *params]
        if one_per_bar:
            sql = (
                f"SELECT * EXCLUDE (_rank) FROM (SELECT *, row_number() OVER"
                f" (PARTITION BY start_time ORDER BY revision DESC) AS _rank FROM {files} WHERE {where})"
                " WHERE _rank = 1 ORDER BY start_time"
            )
        else:
            sql = f"SELECT * FROM {files} WHERE {where} ORDER BY start_time, revision"
        return [row_to_candle(row) for row in self._query(sql, args)]

    def _actions(self, source, instrument_id, start, end, types, *, extra, params=(), one_per_record):
        files = self._action_files(source, instrument_id)
        if files is None:
            return []
        type_sql, type_params = self._types(types)
        where = f"source = ? AND instrument_id = ? AND ex_date >= ? AND ex_date < ? {extra} {type_sql}"
        args = [source, instrument_id, _plain_date(start, "start"), _plain_date(end, "end"), *params, *type_params]
        if one_per_record:
            sql = (
                f"SELECT * EXCLUDE (_rank) FROM (SELECT *, row_number() OVER"
                f" (PARTITION BY action_type, ex_date ORDER BY revision DESC) AS _rank FROM {files} WHERE {where})"
                f" WHERE _rank = 1 ORDER BY ex_date, {_ACTION_RANK}"
            )
        else:
            sql = f"SELECT * FROM {files} WHERE {where} ORDER BY ex_date, {_ACTION_RANK}, revision"
        return [row_to_action(row) for row in self._query(sql, args)]

    @staticmethod
    def _types(types):
        if types is None:
            return "", []
        values = [str(ActionType(t)) for t in types]
        if not values:
            return "AND FALSE", []
        return f"AND action_type IN ({', '.join('?' for _ in values)})", values

    def _candle_files(self, source, instrument_id, timeframe) -> str | None:
        folder = (self.root / "candles" / f"source={source}" / f"instrument_id={instrument_id}"
                  / f"timeframe={Timeframe(timeframe)}")
        return self._files(folder)

    def _action_files(self, source, instrument_id) -> str | None:
        return self._files(self.root / "corporate_actions" / f"source={source}" / f"instrument_id={instrument_id}")

    @staticmethod
    def _files(folder: Path) -> str | None:
        """A read_parquet() over one provider partition's files, or None if there are none."""
        if not folder.is_dir() or not any(folder.glob("import=*.parquet")):
            return None
        pattern = (folder / "import=*.parquet").as_posix().replace("'", "''")
        return f"read_parquet('{pattern}', hive_partitioning = false)"

    @staticmethod
    def _query(sql: str, params: list) -> list[dict]:
        with duckdb.connect(":memory:") as conn:
            return conn.execute(sql, params).fetch_arrow_table().to_pylist()
