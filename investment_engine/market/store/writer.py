"""Append-only writes to the market-data store (Law 8; ADR-009; docs/tasks/M1-10.md).

This is the one place that assigns revision numbers, per identity:
- an identity not stored before becomes revision 1: BACKFILL_ASSUMED at the
  observation's backfill time if it has one, otherwise OBSERVED at receipt;
- for an identity already stored, the observation is validated in full as
  the OBSERVED next revision it would become. Identical compared values then
  write nothing, so an invalid duplicate is refused, not skipped; changed
  values are written as that revision, available from their own receipt.
  Any backfill time supplied is ignored there, so a correction is never
  backdated.

Identities include the provider, so one provider's value is never another's
correction. Every write creates new files only: each partition's new rows go
to <partition>/import=<import_id>.parquet, written under a temporary name and
then linked into place, refusing if the target exists. The whole batch is
validated before any file is written.
"""

import os
import re
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from investment_engine.market.availability import (
    AvailabilityBasis,
    check_instrument_id,
    check_provider,
)
from investment_engine.market.candles import BarState, Candle, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType, AmountBasis, CorporateAction
from investment_engine.market.store.schema import (
    ACTION_SCHEMA,
    CANDLE_SCHEMA,
    action_to_row,
    candle_to_row,
    row_to_action,
    row_to_candle,
    to_table,
)
from investment_engine.money import Money

_IMPORT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")


@dataclass(frozen=True)
class CandleObservation:
    """What an importer saw: a candle's values before a revision and availability are assigned."""

    source: str
    instrument_id: str
    timeframe: Timeframe
    start_time: datetime
    end_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    currency: str
    volume: Decimal
    state: BarState
    source_version: str
    price_basis: PriceBasis
    volume_basis: VolumeBasis
    event_time: datetime
    received_at: datetime
    processed_at: datetime
    backfill_available_from: datetime | None  # for first-seen history; None means observed live


@dataclass(frozen=True)
class ActionObservation:
    """What an importer saw: a corporate action's values before a revision and availability are assigned."""

    source: str
    instrument_id: str
    currency: str
    exchange_timezone: str
    action_type: ActionType
    ex_date: date
    ratio: Decimal | None
    amount: Money | None
    amount_basis: AmountBasis | None
    new_symbol: str | None
    source_version: str
    received_at: datetime
    processed_at: datetime
    backfill_available_from: datetime | None


@dataclass(frozen=True)
class WriteResult:
    new_records: int
    new_revisions: int
    unchanged: int
    import_id: str


def _candle_values(c: Candle | CandleObservation) -> tuple:
    return (c.open, c.high, c.low, c.close, c.volume, c.currency, str(c.price_basis), str(c.volume_basis))


def _action_values(a: CorporateAction | ActionObservation) -> tuple:
    amount_basis = None if a.amount_basis is None else str(a.amount_basis)
    return (a.ratio, a.amount, amount_basis, a.new_symbol)


def _inside(root: Path, folder: Path) -> Path:
    """`folder`, refusing any path that resolves outside the store's root."""
    if not folder.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"{folder} is outside the market-data store at {root}")
    return folder


class MarketDataWriter:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # ---------------------------------------------------------------- public

    def write_candles(self, observations: Sequence[CandleObservation], import_id: str) -> WriteResult:
        return self._write(
            observations,
            import_id,
            kind="candles",
            observation_type=CandleObservation,
            identity=lambda o: (o.source, o.instrument_id, str(Timeframe(o.timeframe)), o.start_time),
            partition=lambda o: (
                f"source={o.source}",
                f"instrument_id={o.instrument_id}",
                f"timeframe={Timeframe(o.timeframe)}",
            ),
            values=_candle_values,
            build=self._build_candle,
            to_row=candle_to_row,
            from_row=row_to_candle,
            schema=CANDLE_SCHEMA,
        )

    def write_corporate_actions(self, observations: Sequence[ActionObservation], import_id: str) -> WriteResult:
        return self._write(
            observations,
            import_id,
            kind="corporate_actions",
            observation_type=ActionObservation,
            identity=lambda o: (o.source, o.instrument_id, str(ActionType(o.action_type)), o.ex_date),
            partition=lambda o: (f"source={o.source}", f"instrument_id={o.instrument_id}"),
            values=_action_values,
            build=CorporateAction,
            to_row=action_to_row,
            from_row=row_to_action,
            schema=ACTION_SCHEMA,
        )

    # ---------------------------------------------------------------- internals

    @staticmethod
    def _build_candle(**values) -> Candle:
        candle = Candle(**values)
        if candle.state is not BarState.CLOSED:
            raise ValueError("only CLOSED bars are stored; a FORMING bar is still changing")
        return candle

    def _write(self, observations, import_id, *, kind, observation_type, identity, partition, values,
               build: Callable, to_row: Callable, from_row: Callable, schema: pa.Schema) -> WriteResult:
        if not isinstance(import_id, str) or not _IMPORT_ID.fullmatch(import_id):
            raise ValueError(f"import_id must be a safe file name (letters, digits, . _ -), not {import_id!r}")

        latest: dict[tuple, object] = {}
        loaded: set[Path] = set()
        pending: dict[Path, list[dict]] = defaultdict(list)
        new_records = new_revisions = unchanged = 0

        for obs in observations:
            if not isinstance(obs, observation_type):
                raise TypeError(f"expected {observation_type.__name__}, not {type(obs).__name__}")
            check_provider(obs.source)
            check_instrument_id(obs.instrument_id)
            folder = _inside(self.root, self.root / kind / Path(*partition(obs)))
            if folder not in loaded:
                for record in self._read_partition(folder, from_row):
                    key = identity(record)
                    if key not in latest or record.revision > latest[key].revision:
                        latest[key] = record
                loaded.add(folder)

            fields_ = {f.name: getattr(obs, f.name) for f in fields(obs) if f.name != "backfill_available_from"}

            def as_record(revision, basis, available_from, fields_=fields_):
                return build(**fields_, import_id=import_id, revision=revision,
                             available_from=available_from, availability_basis=basis)

            # Every observation is validated in full, as the record it would
            # actually become, before deciding whether it's unchanged; the
            # checks run on everything it claims, not on a few compared values.
            key = identity(obs)
            previous = latest.get(key)
            if previous is None:
                if obs.backfill_available_from is not None:
                    new = as_record(1, AvailabilityBasis.BACKFILL_ASSUMED, obs.backfill_available_from)
                else:
                    new = as_record(1, AvailabilityBasis.OBSERVED, obs.received_at)
                new_records += 1
            else:
                # Stored before: the next revision, always observed at its own
                # receipt and never backdated; any backfill time is ignored.
                new = as_record(previous.revision + 1, AvailabilityBasis.OBSERVED, obs.received_at)
                if values(previous) == values(new):
                    unchanged += 1
                    continue
                if obs.received_at < previous.received_at:
                    raise ValueError(
                        f"a correction received at {obs.received_at} is earlier than the revision it corrects "
                        f"({previous.received_at}); revisions are observed in time order"
                    )
                new_revisions += 1

            latest[key] = new
            pending[folder].append(to_row(new))

        # Validate every table and every target before writing anything.
        tables = {folder: to_table(rows, schema) for folder, rows in pending.items()}
        targets = {folder: folder / f"import={import_id}.parquet" for folder in tables}
        for target in targets.values():
            if target.exists():
                raise FileExistsError(f"{target} already exists; the store never overwrites a file")
        for folder, table in tables.items():
            self._create(targets[folder], table)

        return WriteResult(new_records, new_revisions, unchanged, import_id)

    @staticmethod
    def _read_partition(folder: Path, from_row: Callable) -> list:
        if not folder.is_dir():
            return []
        records = []
        for path in sorted(folder.glob("import=*.parquet")):
            records.extend(from_row(row) for row in pq.read_table(path).to_pylist())
        return records

    @staticmethod
    def _create(target: Path, table: pa.Table) -> None:
        """Write `table` to a new file at `target`: temporary name first, then linked into place."""
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            pq.write_table(table, temporary)
            os.link(temporary, target)  # fails if target exists; never replaces a file
        finally:
            temporary.unlink(missing_ok=True)
