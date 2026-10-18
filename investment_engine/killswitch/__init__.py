"""The kill switch: a trading-enabled flag outside the database (Law 15; ADR-006; docs/tasks/M4-04.md).

`flag` is the format and the fail-closed reader the Execution Worker uses.
`admin` is the writer, its lock and its journal, imported only by the Admin
CLI (a layering rule). Nothing else can change the flag.
"""
