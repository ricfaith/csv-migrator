# csv-migrator

Loads every `.csv` file in a folder into its own `NVARCHAR(MAX)` staging
table in SQL Server. Each run drops and recreates the table for every file
it processes.

## Setup

If you are new to Python, use [Python setup (first time)](#python-setup-first-time) at the bottom of this page instead of the command below.

```bash
pip install -r requirements.txt
```

If `pyodbc` fails to build on macOS (error mentioning `sql.h` or
`unixodbc`), run `brew install unixodbc` first, then retry.

You'll also need a SQL Server ODBC driver installed (e.g. "ODBC Driver 18
for SQL Server").

## Configure

On a Mac:

```bash
cp migrate.env.example migrate.env
```

On Windows (Command Prompt):

```bat
copy migrate.env.example migrate.env
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

## Python setup (first time)

A virtual environment is a private folder for this project's Python packages. It keeps them separate from anything else on your computer. You only create it once. Find the appropriate instructions for your operating system.

### Mac

Open Terminal and run these commands one at a time. Replace `/path/to/csv-migrator` with the folder where this project lives on your computer:

```bash
cd /path/to/csv-migrator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

After `source venv/bin/activate`, your prompt should start with `(venv)`. That means the environment is on. Leave that Terminal window open and continue with [Configure](#configure) and [Run](#run).

The next time you open Terminal, you do not create the environment again. Turn it back on, then run the script:

```bash
cd /path/to/csv-migrator
source venv/bin/activate
python migrate_csv.py
```

### Windows

Open Command Prompt and run these commands one at a time. Replace `C:\path\to\csv-migrator` with the folder where this project lives on your computer:

```bat
cd C:\path\to\csv-migrator
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

If `python` is not recognized, use `py -m venv venv` for the second command instead.

After `venv\Scripts\activate`, your prompt should start with `(venv)`. That means the environment is on. Leave that window open and continue with [Configure](#configure) and [Run](#run).

In PowerShell, turn the environment on with `venv\Scripts\Activate.ps1` instead of `venv\Scripts\activate`. If PowerShell says running scripts is disabled, use Command Prompt.

The next time you open Command Prompt, you do not create the environment again. Turn it back on, then run the script:

```bat
cd C:\path\to\csv-migrator
venv\Scripts\activate
python migrate_csv.py
```

### When you are finished

On either Mac or Windows, type `deactivate` and press Enter. That turns the environment off. Closing the window does the same thing.