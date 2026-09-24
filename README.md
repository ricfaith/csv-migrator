# csv-migrator

Loads every `.csv` file in a folder into its own `NVARCHAR(MAX)` staging
table in SQL Server. Each run drops and recreates the table for every file
it processes.

## Setup

```bash
pip install -r requirements.txt
```

If `pyodbc` fails to build on macOS (error mentioning `sql.h` or
`unixodbc`), run `brew install unixodbc` first, then retry.

You'll also need a SQL Server ODBC driver installed (e.g. "ODBC Driver 18
for SQL Server").

## Configure

```bash
cp migrate.env.example migrate.env
```

Edit `migrate.env` with your folder/server/database/user. Leave
`SQL_PASSWORD` blank and either set it as an environment variable or let
the script prompt for it — don't put real passwords in the file.

## Run

```bash
python migrate_csv.py
```

Every value in `migrate.env` can be overridden with a CLI flag
(`--folder`, `--server`, `--database`, `--schema`, `--user`) or an OS
environment variable of the same name (e.g. `SQL_SERVER`). Precedence:
CLI flag > environment variable > `migrate.env` > default.

## Tests

```bash
python -m pytest
```

## Additional Setup

To work on Macs, ensure `unixodbc` and SQL Server ODBC is installed.

```bash
brew install unixodbc
brew install microsoft/mssql-release/msodbcsql18
```