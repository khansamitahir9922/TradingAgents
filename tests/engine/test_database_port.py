"""The Operational Database port and its two adapters (docs/tasks/M3-02.md)."""

from datetime import UTC, date, datetime

import pytest

from investment_engine.lineage.records import LineageStore
from investment_engine.storage.database import (
    AppendOnlyViolation,
    IntegrityViolation,
    TransactionAborted,
    translate_named,
)
from tests.engine.test_lineage import record as lineage_record

AT = datetime(2026, 10, 16, 12, 30, tzinfo=UTC)


# ---------------------------------------------------------------- parameter translation (pure)


@pytest.mark.unit
@pytest.mark.parametrize("sql, expected", [
    ("SELECT * FROM t WHERE a = :a", "SELECT * FROM t WHERE a = %(a)s"),
    ("SELECT :a, :a, :b_2", "SELECT %(a)s, %(a)s, %(b_2)s"),
    ("SELECT x::text FROM t WHERE y = :y", "SELECT x::text FROM t WHERE y = %(y)s"),
    ("SELECT ':not_a_param', 'it''s :also_not' WHERE z = :z", "SELECT ':not_a_param', 'it''s :also_not' WHERE z = %(z)s"),
    ("SELECT 5 % 2 WHERE a LIKE 'x%' AND b = :b", "SELECT 5 %% 2 WHERE a LIKE 'x%%' AND b = %(b)s"),
])
def test_named_parameters_translate_for_postgresql(sql, expected):
    assert translate_named(sql) == expected


@pytest.mark.unit
def test_an_unknown_parameter_name_raises(database):
    with pytest.raises(KeyError, match="missing"):
        database.fetchone("SELECT :present, :missing", {"present": 1})


# ---------------------------------------------------------------- both backends


@pytest.mark.unit
def test_values_round_trip_with_dates_times_and_bytes(database):
    database.execute("INSERT INTO lineage_records VALUES (:id, :inst, :at, :blob)",
                     {"id": "lin-x", "inst": "EQ_US_NVDA", "at": AT, "blob": b"\x01\x02"})
    row = database.fetchone("SELECT lineage_id, instrument_id, generated_at, content FROM lineage_records")
    assert row[0] == "lin-x" and row[1] == "EQ_US_NVDA" and bytes(row[3]) == b"\x01\x02"
    assert database.as_datetime(row[2]) == AT
    if database.backend == "sqlite":
        assert row[2] == AT.isoformat()  # the M1-M2 text format is unchanged
    assert database.as_date(date(2021, 1, 4)) == database.as_date("2021-01-04") == date(2021, 1, 4)


@pytest.mark.unit
def test_append_only_and_integrity_errors_have_the_ports_types(database):
    database.execute("INSERT INTO lineage_records VALUES (:id, 'EQ_US_NVDA', :at, :blob)",
                     {"id": "lin-x", "at": AT, "blob": b"\x01"})
    with pytest.raises(AppendOnlyViolation):
        database.execute("DELETE FROM lineage_records")
    with pytest.raises(IntegrityViolation) as error:
        database.execute("INSERT INTO instruments VALUES ('X', 'BOND', 'USD', 'XNAS', 'UTC', 'ACTIVE', :d, NULL)",
                         {"d": date(2020, 1, 1)})
    assert error.value.kind == "check"


@pytest.mark.unit
def test_a_read_opens_no_transaction_and_others_see_committed_writes(backend):
    first, other = backend.first, backend.make()
    assert first.fetchone("SELECT COUNT(*) FROM lineage_records")[0] == 0
    assert not first.in_transaction
    first.execute("INSERT INTO lineage_records VALUES ('lin-a', 'EQ_US_NVDA', :at, :blob)", {"at": AT, "blob": b"\x01"})
    assert other.fetchone("SELECT COUNT(*) FROM lineage_records")[0] == 1


@pytest.mark.unit
def test_a_managed_write_is_invisible_to_others_until_the_outermost_scope_commits(backend):
    first, other = backend.first, backend.make()
    with first.transaction():
        assert first.in_transaction
        first.execute("INSERT INTO lineage_records VALUES ('lin-a', 'EQ_US_NVDA', :at, :blob)",
                      {"at": AT, "blob": b"\x01"})
        with first.transaction():  # nested: joins, no savepoint
            first.execute("INSERT INTO lineage_records VALUES ('lin-b', 'EQ_US_NVDA', :at, :blob)",
                          {"at": AT, "blob": b"\x02"})
        assert first.in_transaction
        assert other.fetchone("SELECT COUNT(*) FROM lineage_records")[0] == 0
    assert not first.in_transaction
    assert other.fetchone("SELECT COUNT(*) FROM lineage_records")[0] == 2


@pytest.mark.unit
def test_a_failure_in_a_nested_scope_rolls_back_the_outer_writes_even_if_caught(backend):
    first = backend.first
    with pytest.raises(TransactionAborted), first.transaction():
        first.execute("INSERT INTO lineage_records VALUES ('lin-a', 'EQ_US_NVDA', :at, :blob)",
                      {"at": AT, "blob": b"\x01"})
        try:
            with first.transaction():
                first.execute("INSERT INTO lineage_records VALUES ('lin-b', 'EQ_US_NVDA', :at, :blob)",
                              {"at": AT, "blob": b"\x02"})
                raise RuntimeError("inner failure")
        except RuntimeError:
            pass
    assert not first.in_transaction
    assert backend.make().fetchone("SELECT COUNT(*) FROM lineage_records")[0] == 0


@pytest.mark.unit
def test_a_store_write_joins_the_callers_scope(backend):
    first = backend.first
    store = LineageStore(first)
    with pytest.raises(RuntimeError, match="after the append"), first.transaction():
        store.append(lineage_record())
        raise RuntimeError("after the append")
    assert backend.make().fetchone("SELECT COUNT(*) FROM lineage_records")[0] == 0
    store.append(lineage_record())  # without a scope, the store opens and commits its own
    assert backend.make().fetchone("SELECT COUNT(*) FROM lineage_records")[0] == 1


@pytest.mark.unit
def test_raw_driver_connections_are_refused_by_the_stores(tmp_path):
    from investment_engine.storage.sqlite import SqliteInstrumentRepository, open_operational_db

    with pytest.raises(TypeError, match="SqliteDatabase"):
        SqliteInstrumentRepository(open_operational_db(tmp_path / "op.sqlite3"))
