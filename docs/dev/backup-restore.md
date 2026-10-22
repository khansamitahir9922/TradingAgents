# Accounting backup and disposable restore verification

This is the M5 runbook, not an installed schedule. Codex implemented it under
the owner's M5 approval. No owner database has been restored or reset, and no
production backup job was run by the implementer. Earlier M3 databases remain
throwaway; a database you keep needs reviewed migrations, never a reset.

## What a verified backup means

`accounting backup NEW_DIRECTORY` uses PostgreSQL 17's custom-format `pg_dump`
with an exported repeatable-read snapshot. The database row counts and hashes
come from that exact exported snapshot. The exporter stays open until the dump
finishes. `pg_restore --list` must read the dump successfully.

Only afterwards does the job copy closed immutable `.parquet` files. It hashes
the source before and after each copy and hashes the copy, then resolves each
database market reference against its exact provider, instrument, bar/action
identity, revision and import ID in the copied store. Tagged lineage records,
compressed records, journal source receipts and broker fill provenance are
included in that reference inventory.

This is a consistent PostgreSQL snapshot plus a **later immutable market
superset**, not an atomic database/filesystem snapshot. A market partition
created during the dump can be included in the superset. A missing referenced
revision fails verification. Capture start, database completion and final
completion times are recorded separately, using the injected clock (LiveClock
for the actual command). Simulation test clocks can intentionally be fixed.

`manifest.json` is successful only after dump and copied-reference checks pass.
`started.json` remains as evidence. A failure writes `failed.json`, and the
verifier refuses failed/incomplete jobs even if a partially published manifest
exists. Existing destinations are refused. Nothing is pruned automatically.
Checksums detect corruption relative to the locally trusted manifest; they are
not a signature against a malicious writer who can replace both files and hashes.

## Explicit owner-operated backup

Under D42, the default backup root is `<data dir>/backups`, outside the repository.
Use the directory returned by `investment_engine.config.data_dir()` and choose a
new child directory for each job, for example `<data dir>/backups/JOB-ID`. The
CLI deliberately requires that explicit **new job directory** rather than
silently reusing an existing destination. A separately chosen off-disk root is
also supported; the example below illustrates that alternative. Confirm that a
custom data directory and the chosen backup root are outside every checkout.
Backups contain confidential database data and stay uncommitted.

Use the installed environment's Python and an absolute **new** destination:

```powershell
& 'C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe' -m investment_engine accounting backup 'D:/InvestmentPlatform-backups/UNIQUE-JOB-NAME'
& 'C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe' -m investment_engine accounting verify 'D:/InvestmentPlatform-backups/UNIQUE-JOB-NAME'
```

`--pg-bin` may name another verified PostgreSQL 17 installation. The Operational
Database DSN comes from the existing environment variable; never put its value
in a command, task action, log or manifest. Both tool versions and server major
version are checked. This local prototype accepts explicit single-loopback DSNs
only, with no libpq service/options indirection. Clear ambient `PG*` variables;
do not print them. Native tool credentials use a private per-child libpq
environment, with `PGHOSTADDR` pinned to loopback and no default password-file
fallback. Tool failures produce sanitized messages, never captured stderr.

The files copied are the database dump and immutable market files. Environment
files, broker secrets, API keys, kill-switch flags/journals, and application logs
are excluded. Do not put credentials in application database records. A dump of
business history is private data, not a public repository artifact.

Initially retain all jobs, including failed ones. A copy on the same disk does
not protect against disk loss. Choose a separate protected disk/location and
verify permissions and the copy before adopting it operationally.

## Daily Windows schedule: proposal only

With separate owner approval, create one Task Scheduler task after the usual
daily data/accounting processing. Its action should invoke the installed Python
with `-m investment_engine accounting backup NEW_DIRECTORY`, using a wrapper
that constructs a fresh job name and stops on a nonzero exit code. Keep the
DSN solely in the task user's private environment. Do not embed it in the task
XML, arguments or wrapper. Avoid overlapping jobs. Inspect `manifest.json` and
run `accounting verify`; a task process exiting is not evidence of verification.

No task/wrapper is installed or enabled by M5. No automatic deletion policy is
configured. The owner chooses schedule time, destination, retention and off-disk
copy procedure before installation.

## Restore verification without touching owner databases

M5 exposes `storage.backups.restore_disposable` for guarded verification,
not a general restore command. The existing PostgreSQL test fixture creates a
fresh `ie_test_<16 lowercase hex>` database. The function additionally requires
explicit disposable confirmation, rejects nonlocal/service/owner names before
connecting, and refuses every nonempty target. It never drops or resets a target.
The root test connection guard still applies to Python connections; native tools
receive separately pinned, sanitized settings.

`pg_restore --exit-on-error --no-owner --no-privileges` loads only that empty
target. All restored user-table row counts and hashes must equal the exported
snapshot's manifest, preserving journal/audit/source records and their content
IDs. Market references are checked again. Domain tests compare balances/P&L
and unit conservation as well. No migrations or history rewrites run on restore.

Verification requires a **new isolated control directory**. No flag or secret
is copied or written there; a missing flag leaves the kill-switch reader disabled.
No worker is started. Any later manual test process must point explicitly at this
isolated control/data configuration, never the owner's enabled global settings.

Run the package's PostgreSQL-marked backup tests through the redacting runner.
They create and clean up only their own disposable databases. Retain failure
evidence for inspection. Restoring an owner database, changing its configuration,
installing a schedule or enabling execution needs a separate explicit owner
instruction and a reviewed operational procedure; M5 authorizes none of those.
