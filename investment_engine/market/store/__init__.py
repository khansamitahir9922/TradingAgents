"""The Market-Data Store: append-only Parquet files, queried with DuckDB (architecture Part E; ADR-009).

The writer and reader import pyarrow and duckdb, which come from the optional
`engine` extra. This package itself imports nothing heavy, so the rest of
investment_engine works without them.
"""
