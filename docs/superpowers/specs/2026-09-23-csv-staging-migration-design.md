# CSV → SQL Server Staging Migration Script

## Problem

An existing T-SQL script (`RailstoTrails_ImportScript20260320.sql`) bulk-loads a
folder of CSV files into SQL Server staging tables using `xp_cmdshell` (to list
files) and `BULK INSERT` (to load them). It's unreliable because:

- `BULK INSERT`/T-SQL has no real CSV parser — fields containing embedded
  commas, quotes, or newlines break row/column splitting. The script's own
  comments admit this is unsolved ("CAN'T GET IT TO FIGURE OUT HOW TO
  INCORPORATE QUOTED IDENTIFIERS").
- Header parsing via `STRING_SPLIT` on a raw comma has the same fragility.
- Heavy use of dynamic SQL and cursors makes it hard to debug.
- `xp_cmdshell` requires elevated server config and is a security smell.
- A known bug: turning `@DebugMode` off breaks the script (errant `END`).

## Goal

A Python script that points at a directory of CSV files and reliably loads
each one into its own staging table in SQL Server, doing the file/CSV parsing
in Python (which has correct CSV handling) and only using SQL Server for
table creation and data loading.

## Non-goals

- Type inference / typed staging columns — everything lands as
  `NVARCHAR(MAX)`; type casting/validation happens later when moving from
  staging into real tables.
- Incremental/append loads across runs — each run drops and recreates the
  table for every CSV it processes.
- Server-side `BULK INSERT`/`TABLOCK` performance path — not built now. Noted
  as a future option if the script ends up running colocated with the SQL
  Server (see "Future options").

## Configuration

All settings are loadable from an env-style file, with CLI args and OS
environment variables available as overrides.

**Precedence (highest wins):** CLI arg → OS environment variable → value from
the env file → built-in default (only `SQL_SCHEMA` has a default: `dbo`;
everything else is required).

**Keys** (in `migrate.env`, simple `KEY=VALUE` lines, `#` comments allowed):

```
CSV_FOLDER=/path/to/csvs
SQL_SERVER=myhost.example.com
SQL_DATABASE=Staging1
SQL_SCHEMA=dbo
SQL_USER=myuser
SQL_PASSWORD=          # prefer leaving blank; set via env var or prompt instead
```

- Default env file path: `./migrate.env`, overridable with `--env-file`.
- `migrate.env.example` is checked into the repo with placeholder values;
  `migrate.env` itself is gitignored.
- `SQL_PASSWORD` resolution order: OS env var `SQL_PASSWORD` → value in the
  env file → interactive `getpass` prompt. Never accepted as a bare CLI arg
  (would leak into shell history).
- Parsing is done with a small stdlib `KEY=VALUE` reader — no new dependency
  (e.g. `python-dotenv`) needed for this.

## Architecture

Single script: `migrate_csv.py`.

```
python migrate_csv.py [--env-file migrate.env] [--folder ...] [--server ...] ...
```

Connects to SQL Server via `pyodbc` using SQL Server authentication
(username/password). This works regardless of whether the script runs on the
DB server itself or a remote client machine, since it streams rows over the
wire rather than depending on the SQL Server process being able to read a
local file path.

### Per-file flow

One file's failure must not stop the others — each file is processed inside
its own try/except.

1. **Discover files** — non-recursive glob for `*.csv` in `CSV_FOLDER`.
2. **Derive table name** from the filename: replace spaces, `-`, `.`, `(`,
   `)`, `[`, `]`, `&` with `_`; collapse repeated underscores; prefix
   `Table_` if the result would start with a digit.
3. **Parse the file** with Python's `csv` module (`csv.reader`), which
   correctly handles quoted fields with embedded commas/newlines — the
   specific thing the T-SQL version couldn't do. Try `utf-8-sig` first (also
   handles a BOM), fall back to `latin-1` on decode error.
4. **Read + sanitize the header row**: apply the same character-replacement
   rule as table names to each column name, then dedupe collisions by
   appending `_1`, `_2`, ... in order of first appearance.
5. **Create the table**: `DROP TABLE IF EXISTS [schema].[table]` followed by
   `CREATE TABLE` with one `NVARCHAR(MAX)` column per sanitized header.
6. **Load data**: stream remaining rows to SQL Server in batches of ~5,000
   using `pyodbc` with `fast_executemany=True` and a parameterized
   `INSERT INTO ... VALUES (?, ?, ...)`. Rows whose column count doesn't
   match the header are logged with their line number and skipped rather
   than aborting the file.
7. **Log** rows loaded and elapsed time for the file.

### Summary report

After all files are processed, print:
- Files processed / succeeded / failed counts.
- Total rows loaded.
- A final row-count-per-table query (mirrors the original script's tail
  query) against `sys.tables` / `sys.dm_db_partition_stats`, filtered to the
  schema being loaded into.

## Error handling

- **Per-file isolation**: exceptions (encoding errors, malformed CSV,
  connection issues on a given file's load) are caught, logged with the
  filename, and processing continues to the next file. The file is counted
  as failed in the summary.
- **Per-row tolerance**: a data row with a column count mismatch against the
  header is logged (filename + line number) and skipped; it does not fail
  the whole file.
- **Connection/auth errors** at startup (bad server/credentials) are fatal —
  there's no point continuing to the next file if we can't connect at all.

## Testing

- Unit tests (pytest) for the pure functions: table-name sanitizing and
  header sanitizing/deduping, covering special characters, leading digits,
  and duplicate headers.
- Manually verify CSV parsing against a couple of hand-built sample files:
  one with embedded commas/quotes/newlines inside quoted fields, one with
  duplicate headers.
- The SQL Server load step can only be verified against a real reachable SQL
  Server instance. If none is available at implementation time, this will be
  called out explicitly as unverified rather than claimed to work.

## Future options (not building now)

- If the script ends up running on the SQL Server box itself (or a path the
  SQL Server process can read directly, e.g. a UNC share it has access to),
  the load step could switch to server-side `BULK INSERT ... WITH (TABLOCK,
  FORMAT='CSV', FIELDQUOTE='"')` for significantly faster loads on very large
  files, per the minimal-logging pattern described in the Elvity article on
  bulk-loading CSVs into SQL Server. Not built now since the deployment
  location is undetermined and the pyodbc path works either way.
