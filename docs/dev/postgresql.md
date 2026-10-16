# Local PostgreSQL for development and tests

From M3 the Operational Database is PostgreSQL (ADR-008). This page sets up a local server on Windows 11 and the test connection, with no secret in the repository (docs/tasks/M3-00.md).

## 1. Install
1. Download the **PostgreSQL 17** Windows x86-64 installer from <https://www.postgresql.org/download/windows/> (the EDB installer).
2. Run it and keep the defaults: install directory, data directory, port **5432**, default locale. Keep the components **PostgreSQL Server**, **pgAdmin 4** and **Command Line Tools**. Stack Builder isn't needed.
3. Choose a password for the `postgres` administrator account and keep it somewhere safe. It's needed only for step 3.
4. If Windows Firewall asks, don't allow access. The server is for this computer only.

## 2. Local connections only
The installer makes the server listen on every network interface. Restrict it to this machine:
1. Open Notepad **as administrator** and open `C:\Program Files\PostgreSQL\17\data\postgresql.conf` (set the file filter to *All Files*).
2. Set `listen_addresses = 'localhost'`.
3. Save, then restart the Windows service **postgresql-x64-17** (Services, right-click, Restart).

`pg_hba.conf` already accepts logins only from `127.0.0.1/32` and `::1/128`. Leave it that way.

## 3. A dedicated role
Open **SQL Shell (psql)**, press Enter at the four prompts (server `localhost`, database `postgres`, port `5432`, user `postgres`) and enter the administrator password. Then run the line below with your own password (letters and digits only):
```sql
CREATE ROLE ie_dev LOGIN CREATEDB PASSWORD '<choose one>';
```
The role can create databases but isn't a superuser. Leave with `\q`.

## 4. The test connection
Create a **Windows user** environment variable (Start → "Edit environment variables for your account" → New):

- **Name:** `INVESTMENT_ENGINE_TEST_PG_DSN`
- **Value:** `host=localhost port=5432 dbname=postgres user=ie_dev password=<your password>`

Restart VS Code and any terminal so they see it. Never put the password in `.env`, a commit or a chat. Code and tests refer only to the variable's name, and never print its value.

## How the tests use it
- Tests marked `postgres` each get a new database, `ie_test_<random hex>`, created from `template0` and dropped afterwards, even when the test fails.
- Without the variable those tests **skip** with the reason "PostgreSQL test DSN not set (see docs/dev/postgresql.md)". From M3 on, a check run counts only if no `postgres` test skipped.
- **Every connection is guarded** (`tests/conftest.py`):
  - Tests without the `postgres` marker can't connect at all.
  - For `postgres` tests, every `PG*` environment variable is removed.
  - Only the keywords `host`, `port`, `dbname`, `user`, `password`, `connect_timeout`, `application_name` and `sslmode` are accepted. The host must be a single `localhost`, `127.0.0.1` or `::1`, and `hostaddr` is pinned to the numeric loopback address.
  - `hostaddr`, `service`, multi-host lists and other keywords are refused. Refusals name the keyword, never its value.
- In CI, the test job runs a `postgres:17` service with a throwaway password defined in the workflow.
