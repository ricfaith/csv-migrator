# CSV → SQL Server Staging Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `migrate_csv.py`, a script that points at a directory of CSV files and reliably loads each one into its own `NVARCHAR(MAX)` staging table in SQL Server, replacing the fragile T-SQL/`BULK INSERT` approach.

**Architecture:** A small `csv_migrator` package (config loading, identifier sanitizing, CSV parsing, DB operations) with pure/mockable functions, orchestrated by a thin `migrate_csv.py` CLI script. All config comes from CLI args / OS env vars / an env file, with CLI > env var > env file > default precedence.

**Tech Stack:** Python 3, `pyodbc`, `pytest` (stdlib `csv`, `argparse`, `getpass`, `logging`, `glob` for everything else — no other third-party dependencies).

## Global Constraints

- Config precedence, highest wins: CLI arg → OS environment variable → env file value → built-in default. Only `SQL_SCHEMA` has a default (`dbo`); `CSV_FOLDER`, `SQL_SERVER`, `SQL_DATABASE`, `SQL_USER` are required with no default.
- Env file default path is `./migrate.env`, overridable with `--env-file`. `migrate.env` is gitignored; `migrate.env.example` (placeholder values) is checked in.
- `SQL_PASSWORD` is never accepted as a bare CLI arg — only OS env var, env file, or an interactive prompt.
- Every staging table column is `NVARCHAR(MAX)`. No type inference.
- Each run drops and recreates the table for every CSV file it processes (no truncate-only, no append mode).
- File discovery is a non-recursive glob for `*.csv` directly inside `CSV_FOLDER`.
- CSV parsing uses Python's `csv` module, not SQL Server `BULK INSERT`, specifically to handle quoted fields with embedded commas/newlines correctly.
- Data loading uses `pyodbc` with `fast_executemany=True`, in batches of ~5,000 rows.
- A single file's failure is caught, logged, and processing continues with the next file. A single row's column-count mismatch against the header is logged and skipped, not fatal to the file.
- No new dependency for env-file parsing (no `python-dotenv`) — a stdlib `KEY=VALUE` reader is sufficient.
- `db.py` must not import `pyodbc` at module level — only inside `connect()` — so the rest of the test suite doesn't require `pyodbc` (and its native ODBC driver dependency) to be installed.

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `migrate.env.example`
- Create: `csv_migrator/__init__.py`
- Create: `tests/fixtures/quoted_fields.csv`
- Create: `tests/fixtures/duplicate_headers.csv`

**Interfaces:**
- Produces: an importable, empty `csv_migrator` package; two fixture CSV files reused by Tasks 4 and 6.

- [ ] **Step 1: Create the package and dependency files**

`requirements.txt`:
```
pyodbc>=5.0
pytest>=8.0
```

`csv_migrator/__init__.py`:
```python
```

- [ ] **Step 2: Create the env file example**

`migrate.env.example`:
```
# Copy this file to migrate.env and fill in real values.
# migrate.env is gitignored - never commit real credentials.

CSV_FOLDER=/path/to/csvs
SQL_SERVER=myhost.example.com
SQL_DATABASE=Staging1
SQL_SCHEMA=dbo
SQL_USER=myuser

# Prefer leaving SQL_PASSWORD blank here and setting it via the
# SQL_PASSWORD environment variable instead, or just let the script
# prompt for it interactively.
SQL_PASSWORD=
```

- [ ] **Step 3: Create fixture CSV files used by later tasks**

`tests/fixtures/quoted_fields.csv` (note: write this file with real newlines inside the quoted field, exactly as shown — it must be 4 physical lines, not 3):
```
Name,Notes,Amount
"Smith, John","Line one
line two",100
Jane,"Has ""quotes"" inside",200
```

`tests/fixtures/duplicate_headers.csv`:
```
Name,Amount,Name,Amount
Alice,10,alice2,20
```

- [ ] **Step 4: Install dependencies**

Run: `pip install -r requirements.txt`

Expected: installs cleanly. If `pyodbc` fails to build on macOS with an error mentioning `sql.h` or `unixodbc`, run `brew install unixodbc` first, then retry.

- [ ] **Step 5: Verify test infrastructure**

Run: `python -m pytest --collect-only`
Expected: `no tests ran` (or `0 items`) with no collection errors.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt migrate.env.example csv_migrator/__init__.py tests/fixtures/
git commit -m "chore: scaffold csv-migrator project"
```

---

### Task 2: Identifier sanitizing

**Files:**
- Create: `csv_migrator/sanitize.py`
- Test: `tests/test_sanitize.py`

**Interfaces:**
- Produces: `sanitize_identifier(name: str) -> str`, `table_name_from_filename(filename: str) -> str`, `dedupe_headers(headers: list[str]) -> list[str]` — used by Task 6's `process_file`.

- [ ] **Step 1: Write the failing tests**

`tests/test_sanitize.py`:
```python
from csv_migrator.sanitize import sanitize_identifier, table_name_from_filename, dedupe_headers


def test_replaces_spaces_and_punctuation_with_underscore():
    assert sanitize_identifier("First Name") == "First_Name"
    assert sanitize_identifier("Order-Date (2024)") == "Order_Date_2024"


def test_collapses_repeated_underscores():
    assert sanitize_identifier("A -- B") == "A_B"


def test_prefixes_leading_digit_with_table():
    assert sanitize_identifier("2024_Sales") == "Table_2024_Sales"


def test_empty_name_becomes_column():
    assert sanitize_identifier("") == "Column"
    assert sanitize_identifier("   ") == "Column"


def test_table_name_from_filename_strips_csv_extension():
    assert table_name_from_filename("Rails to Trails.csv") == "Rails_to_Trails"
    assert table_name_from_filename("2024-data.csv") == "Table_2024_data"


def test_dedupe_headers_appends_suffix_for_duplicates():
    assert dedupe_headers(["Name", "Amount", "Name", "Amount"]) == [
        "Name", "Amount", "Name_1", "Amount_1",
    ]


def test_dedupe_headers_sanitizes_each_name():
    assert dedupe_headers(["First Name", "", "First Name"]) == [
        "First_Name", "Column", "First_Name_1",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sanitize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'csv_migrator.sanitize'`

- [ ] **Step 3: Implement**

`csv_migrator/sanitize.py`:
```python
import re

_INVALID_CHARS = re.compile(r"[ \-.()\[\]&]")
_REPEATED_UNDERSCORE = re.compile(r"_+")


def sanitize_identifier(name: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", name)
    cleaned = _REPEATED_UNDERSCORE.sub("_", cleaned)
    cleaned = cleaned.strip("_") or "Column"
    if cleaned[0].isdigit():
        cleaned = "Table_" + cleaned
    return cleaned


def table_name_from_filename(filename: str) -> str:
    stem = filename
    if stem.lower().endswith(".csv"):
        stem = stem[:-4]
    return sanitize_identifier(stem)


def dedupe_headers(headers: list[str]) -> list[str]:
    sanitized = [sanitize_identifier(h) for h in headers]
    seen: dict[str, int] = {}
    result = []
    for name in sanitized:
        if name not in seen:
            seen[name] = 0
            result.append(name)
        else:
            seen[name] += 1
            result.append(f"{name}_{seen[name]}")
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sanitize.py -v`
Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add csv_migrator/sanitize.py tests/test_sanitize.py
git commit -m "feat: add identifier sanitizing for table/column names"
```

---

### Task 3: Configuration loading

**Files:**
- Create: `csv_migrator/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Config` dataclass with fields `csv_folder, sql_server, sql_database, sql_schema, sql_user, sql_password` (all `str`); `build_config(argv: list[str] | None = None) -> Config` — used by Task 6's `main()`.

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:
```python
import getpass as getpass_module

import pytest

from csv_migrator.config import parse_env_file, resolve_value, resolve_password, build_config

_ALL_KEYS = ["CSV_FOLDER", "SQL_SERVER", "SQL_DATABASE", "SQL_SCHEMA", "SQL_USER", "SQL_PASSWORD"]


def _clear_env(monkeypatch):
    for key in _ALL_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_parse_env_file_skips_comments_and_blank_lines(tmp_path):
    env_path = tmp_path / "migrate.env"
    env_path.write_text(
        "# comment\n"
        "\n"
        "CSV_FOLDER=/data/csvs\n"
        "SQL_SERVER = myhost \n"
    )
    values = parse_env_file(str(env_path))
    assert values == {"CSV_FOLDER": "/data/csvs", "SQL_SERVER": "myhost"}


def test_parse_env_file_missing_file_returns_empty_dict(tmp_path):
    assert parse_env_file(str(tmp_path / "nope.env")) == {}


def test_resolve_value_precedence_cli_wins(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SQL_SERVER", "env-host")
    result = resolve_value("sql_server", "cli-host", {"SQL_SERVER": "file-host"})
    assert result == "cli-host"


def test_resolve_value_precedence_env_var_over_file(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SQL_SERVER", "env-host")
    result = resolve_value("sql_server", None, {"SQL_SERVER": "file-host"})
    assert result == "env-host"


def test_resolve_value_precedence_file_over_default(monkeypatch):
    _clear_env(monkeypatch)
    result = resolve_value("sql_server", None, {"SQL_SERVER": "file-host"}, default="fallback")
    assert result == "file-host"


def test_resolve_value_falls_back_to_default(monkeypatch):
    _clear_env(monkeypatch)
    result = resolve_value("sql_schema", None, {}, default="dbo")
    assert result == "dbo"


def test_resolve_password_falls_back_to_file_value(monkeypatch):
    _clear_env(monkeypatch)
    result = resolve_password({"SQL_PASSWORD": "file-secret"})
    assert result == "file-secret"


def test_resolve_password_prompts_when_not_set(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr(getpass_module, "getpass", lambda prompt="": "typed-secret")
    result = resolve_password({})
    assert result == "typed-secret"


def test_build_config_raises_on_missing_required(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    empty_env = tmp_path / "migrate.env"
    empty_env.write_text("")
    with pytest.raises(SystemExit):
        build_config(["--env-file", str(empty_env)])


def test_build_config_resolves_from_env_file(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    env_path = tmp_path / "migrate.env"
    env_path.write_text(
        "CSV_FOLDER=/data\nSQL_SERVER=host\nSQL_DATABASE=Staging1\nSQL_USER=me\nSQL_PASSWORD=secret\n"
    )
    config = build_config(["--env-file", str(env_path)])
    assert config.csv_folder == "/data"
    assert config.sql_server == "host"
    assert config.sql_database == "Staging1"
    assert config.sql_schema == "dbo"
    assert config.sql_user == "me"
    assert config.sql_password == "secret"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'csv_migrator.config'`

- [ ] **Step 3: Implement**

`csv_migrator/config.py`:
```python
import argparse
import getpass
import os
from dataclasses import dataclass


@dataclass
class Config:
    csv_folder: str
    sql_server: str
    sql_database: str
    sql_schema: str
    sql_user: str
    sql_password: str


_ENV_KEY_MAP = {
    "csv_folder": "CSV_FOLDER",
    "sql_server": "SQL_SERVER",
    "sql_database": "SQL_DATABASE",
    "sql_schema": "SQL_SCHEMA",
    "sql_user": "SQL_USER",
}


def parse_env_file(path: str) -> dict:
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def resolve_value(key, cli_value, env_file_values, default=None):
    if cli_value:
        return cli_value
    env_key = _ENV_KEY_MAP[key]
    if os.environ.get(env_key):
        return os.environ[env_key]
    if env_file_values.get(env_key):
        return env_file_values[env_key]
    return default


def resolve_password(env_file_values: dict) -> str:
    if os.environ.get("SQL_PASSWORD"):
        return os.environ["SQL_PASSWORD"]
    if env_file_values.get("SQL_PASSWORD"):
        return env_file_values["SQL_PASSWORD"]
    return getpass.getpass("SQL Server password: ")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate a folder of CSV files into SQL Server staging tables."
    )
    parser.add_argument("--env-file", default="migrate.env")
    parser.add_argument("--folder", dest="csv_folder")
    parser.add_argument("--server", dest="sql_server")
    parser.add_argument("--database", dest="sql_database")
    parser.add_argument("--schema", dest="sql_schema")
    parser.add_argument("--user", dest="sql_user")
    return parser


def build_config(argv=None) -> Config:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    env_file_values = parse_env_file(args.env_file)

    resolved = {}
    missing = []
    for key in ["csv_folder", "sql_server", "sql_database", "sql_user"]:
        value = resolve_value(key, getattr(args, key), env_file_values)
        if not value:
            missing.append(_ENV_KEY_MAP[key])
        resolved[key] = value

    if missing:
        raise SystemExit(
            "Missing required configuration: " + ", ".join(missing)
            + ". Set via CLI arg, environment variable, or the env file."
        )

    schema = resolve_value("sql_schema", args.sql_schema, env_file_values, default="dbo")
    password = resolve_password(env_file_values)

    return Config(
        csv_folder=resolved["csv_folder"],
        sql_server=resolved["sql_server"],
        sql_database=resolved["sql_database"],
        sql_schema=schema,
        sql_user=resolved["sql_user"],
        sql_password=password,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add csv_migrator/config.py tests/test_config.py
git commit -m "feat: add env-file/CLI/env-var configuration loading"
```

---

### Task 4: CSV parsing

**Files:**
- Create: `csv_migrator/csv_reader.py`
- Test: `tests/test_csv_reader.py`

**Interfaces:**
- Consumes: fixture files from Task 1 (`tests/fixtures/quoted_fields.csv`, `tests/fixtures/duplicate_headers.csv`).
- Produces: `read_header_and_rows(path: str) -> tuple[TextIO, list[str], csv.reader]` and `validated_rows(rows: Iterable[list[str]], expected_columns: int, filename: str) -> Iterator[list[str]]` — used by Task 6's `process_file`.

- [ ] **Step 1: Write the failing tests**

`tests/test_csv_reader.py`:
```python
import os

from csv_migrator.csv_reader import read_header_and_rows, validated_rows

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_quoted_fields_parsed_correctly():
    path = os.path.join(FIXTURES_DIR, "quoted_fields.csv")
    f, header, reader = read_header_and_rows(path)
    try:
        rows = list(reader)
    finally:
        f.close()
    assert header == ["Name", "Notes", "Amount"]
    assert rows == [
        ["Smith, John", "Line one\nline two", "100"],
        ["Jane", 'Has "quotes" inside', "200"],
    ]


def test_duplicate_headers_read_raw():
    path = os.path.join(FIXTURES_DIR, "duplicate_headers.csv")
    f, header, reader = read_header_and_rows(path)
    try:
        rows = list(reader)
    finally:
        f.close()
    assert header == ["Name", "Amount", "Name", "Amount"]
    assert rows == [["Alice", "10", "alice2", "20"]]


def test_validated_rows_skips_mismatched_row_count(caplog):
    rows = iter([
        ["a", "1"],
        ["b"],
        ["c", "3"],
    ])
    with caplog.at_level("WARNING"):
        result = list(validated_rows(rows, expected_columns=2, filename="test.csv"))
    assert result == [["a", "1"], ["c", "3"]]
    assert "test.csv" in caplog.text
    assert "line 3" in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_csv_reader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'csv_migrator.csv_reader'`

- [ ] **Step 3: Implement**

`csv_migrator/csv_reader.py`:
```python
import csv
import logging

logger = logging.getLogger(__name__)


def open_csv_reader(path):
    try:
        f = open(path, "r", encoding="utf-8-sig", newline="")
        f.read()
        f.seek(0)
    except UnicodeDecodeError:
        f.close()
        f = open(path, "r", encoding="latin-1", newline="")
    return f, csv.reader(f)


def read_header_and_rows(path):
    f, reader = open_csv_reader(path)
    header = next(reader)
    return f, header, reader


def validated_rows(rows, expected_columns, filename):
    for line_number, row in enumerate(rows, start=2):
        if len(row) != expected_columns:
            logger.warning(
                "%s: line %d: expected %d columns, got %d - skipping",
                filename, line_number, expected_columns, len(row),
            )
            continue
        yield row
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_csv_reader.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add csv_migrator/csv_reader.py tests/test_csv_reader.py
git commit -m "feat: add CSV parsing with correct quote/newline handling"
```

---

### Task 5: Database operations

**Files:**
- Create: `csv_migrator/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `quote_identifier(name: str) -> str`, `create_table(conn, schema: str, table: str, columns: list[str]) -> None`, `load_rows(conn, schema: str, table: str, columns: list[str], rows: Iterable[list[str]], batch_size: int = 5000) -> int`, `summary_report(conn, schema: str) -> list[tuple[str, int]]`, `connect(config) -> pyodbc.Connection` — used by Task 6's `process_file`, `run`, and `main`.

- [ ] **Step 1: Write the failing tests**

`tests/test_db.py`:
```python
from unittest.mock import MagicMock

from csv_migrator.db import quote_identifier, create_table, load_rows, summary_report


def test_quote_identifier_wraps_and_escapes_brackets():
    assert quote_identifier("MyTable") == "[MyTable]"
    assert quote_identifier("Weird]Name") == "[Weird]]Name]"


def test_create_table_drops_then_creates():
    conn = MagicMock()
    cursor = conn.cursor.return_value

    create_table(conn, "dbo", "MyTable", ["Col_A", "Col_B"])

    drop_sql = cursor.execute.call_args_list[0].args[0]
    create_sql = cursor.execute.call_args_list[1].args[0]
    assert "DROP TABLE" in drop_sql
    assert "[dbo].[MyTable]" in drop_sql
    assert create_sql == "CREATE TABLE [dbo].[MyTable] ([Col_A] NVARCHAR(MAX), [Col_B] NVARCHAR(MAX))"
    conn.commit.assert_called_once()


def test_load_rows_batches_and_returns_total_count():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    rows = [["a", "1"], ["b", "2"], ["c", "3"]]

    total = load_rows(conn, "dbo", "MyTable", ["Col_A", "Col_B"], iter(rows), batch_size=2)

    assert total == 3
    assert cursor.executemany.call_count == 2
    assert cursor.fast_executemany is True


def test_summary_report_returns_table_and_row_count_pairs():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchall.return_value = [("MyTable", 100), ("OtherTable", 5)]

    result = summary_report(conn, "dbo")

    assert result == [("MyTable", 100), ("OtherTable", 5)]
    cursor.execute.assert_called_once()
    args, _ = cursor.execute.call_args
    assert "sys.tables" in args[0]
    assert args[1] == "dbo"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'csv_migrator.db'`

- [ ] **Step 3: Implement**

`csv_migrator/db.py`:
```python
def connect(config):
    import pyodbc

    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={config.sql_server};"
        f"DATABASE={config.sql_database};"
        f"UID={config.sql_user};"
        f"PWD={config.sql_password};"
        "TrustServerCertificate=yes;"
    )
    conn = pyodbc.connect(conn_str)
    conn.autocommit = False
    return conn


def quote_identifier(name):
    return "[" + name.replace("]", "]]") + "]"


def create_table(conn, schema, table, columns):
    cursor = conn.cursor()
    qualified = f"{quote_identifier(schema)}.{quote_identifier(table)}"
    cursor.execute(f"IF OBJECT_ID('{schema}.{table}', 'U') IS NOT NULL DROP TABLE {qualified}")
    column_defs = ", ".join(f"{quote_identifier(c)} NVARCHAR(MAX)" for c in columns)
    cursor.execute(f"CREATE TABLE {qualified} ({column_defs})")
    conn.commit()


def load_rows(conn, schema, table, columns, rows, batch_size=5000):
    cursor = conn.cursor()
    cursor.fast_executemany = True
    qualified = f"{quote_identifier(schema)}.{quote_identifier(table)}"
    placeholders = ", ".join("?" for _ in columns)
    insert_sql = f"INSERT INTO {qualified} VALUES ({placeholders})"

    total = 0
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            cursor.executemany(insert_sql, batch)
            conn.commit()
            total += len(batch)
            batch = []
    if batch:
        cursor.executemany(insert_sql, batch)
        conn.commit()
        total += len(batch)
    return total


def summary_report(conn, schema):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT t.name, s.row_count
        FROM sys.tables t
        JOIN sys.dm_db_partition_stats s ON t.object_id = s.object_id
        JOIN sys.schemas sc ON t.schema_id = sc.schema_id
        WHERE s.row_count > 0 AND t.type_desc = 'USER_TABLE' AND sc.name = ?
        ORDER BY s.row_count DESC
        """,
        schema,
    )
    return [(row[0], row[1]) for row in cursor.fetchall()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_db.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add csv_migrator/db.py tests/test_db.py
git commit -m "feat: add table create/load/summary DB operations"
```

---

### Task 6: Orchestration script and usage docs

**Files:**
- Create: `migrate_csv.py`
- Create: `README.md`
- Test: `tests/test_migrate_csv.py`

**Interfaces:**
- Consumes: `Config`/`build_config` (Task 3), `read_header_and_rows`/`validated_rows` (Task 4), `quote_identifier`/`create_table`/`load_rows`/`summary_report`/`connect` (Task 5), `dedupe_headers`/`table_name_from_filename` (Task 2).
- Produces: `discover_csv_files(folder: str) -> list[str]`, `process_file(conn, schema: str, path: str) -> tuple[str, int]`, `run(config, conn) -> None`, `main(argv=None) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_migrate_csv.py`:
```python
import os
from unittest.mock import MagicMock

from csv_migrator.config import Config
from migrate_csv import discover_csv_files, process_file, run

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_discover_csv_files_finds_only_csv_non_recursive(tmp_path):
    (tmp_path / "a.csv").write_text("h1,h2\n1,2\n")
    (tmp_path / "b.csv").write_text("h1\n1\n")
    (tmp_path / "notes.txt").write_text("ignore me")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.csv").write_text("h1\n1\n")

    files = discover_csv_files(str(tmp_path))

    names = sorted(os.path.basename(f) for f in files)
    assert names == ["a.csv", "b.csv"]


def test_process_file_creates_table_and_loads_rows():
    conn = MagicMock()
    path = os.path.join(FIXTURES_DIR, "quoted_fields.csv")

    table, count = process_file(conn, "dbo", path)

    assert table == "quoted_fields"
    assert count == 2
    conn.cursor.return_value.execute.assert_any_call(
        "CREATE TABLE [dbo].[quoted_fields] ([Name] NVARCHAR(MAX), [Notes] NVARCHAR(MAX), [Amount] NVARCHAR(MAX))"
    )


def test_run_continues_after_one_file_fails(tmp_path, caplog, monkeypatch):
    (tmp_path / "good.csv").write_text("Name,Amount\nAlice,10\nBob,20\n")
    (tmp_path / "bad.csv").write_text("X,Y\n1,2\n")

    import migrate_csv

    def fake_create_table(conn, schema, table, columns):
        if table == "bad":
            raise RuntimeError("boom")

    monkeypatch.setattr(migrate_csv, "create_table", fake_create_table)
    monkeypatch.setattr(migrate_csv, "load_rows", lambda *a, **k: 2)
    monkeypatch.setattr(migrate_csv, "summary_report", lambda *a, **k: [])

    conn = MagicMock()
    config = Config(
        csv_folder=str(tmp_path),
        sql_server="host",
        sql_database="db",
        sql_schema="dbo",
        sql_user="user",
        sql_password="pw",
    )

    with caplog.at_level("INFO"):
        run(config, conn)

    assert "Succeeded: 1" in caplog.text
    assert "Failed: 1" in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_migrate_csv.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'migrate_csv'`

- [ ] **Step 3: Implement**

`migrate_csv.py`:
```python
#!/usr/bin/env python3
import glob
import logging
import os
import time

from csv_migrator.config import build_config
from csv_migrator.csv_reader import read_header_and_rows, validated_rows
from csv_migrator.db import connect, create_table, load_rows, summary_report
from csv_migrator.sanitize import dedupe_headers, table_name_from_filename

logger = logging.getLogger("migrate_csv")


def discover_csv_files(folder):
    return sorted(glob.glob(os.path.join(folder, "*.csv")))


def process_file(conn, schema, path):
    filename = os.path.basename(path)
    table = table_name_from_filename(filename)
    f, raw_header, reader = read_header_and_rows(path)
    try:
        columns = dedupe_headers(raw_header)
        create_table(conn, schema, table, columns)
        rows = validated_rows(reader, len(columns), filename)
        count = load_rows(conn, schema, table, columns, rows)
        return table, count
    finally:
        f.close()


def run(config, conn):
    csv_files = discover_csv_files(config.csv_folder)
    if not csv_files:
        logger.info("No CSV files found in %s", config.csv_folder)
        return

    succeeded = 0
    failed = 0
    total_rows = 0
    start_all = time.time()

    for path in csv_files:
        filename = os.path.basename(path)
        start = time.time()
        try:
            table, count = process_file(conn, config.sql_schema, path)
            total_rows += count
            succeeded += 1
            logger.info(
                "%s: loaded %d rows into %s.%s (%.1fs)",
                filename, count, config.sql_schema, table, time.time() - start,
            )
        except Exception as exc:
            failed += 1
            logger.error("%s: FAILED - %s", filename, exc)

    logger.info("")
    logger.info("=== Summary ===")
    logger.info("Files processed: %d", len(csv_files))
    logger.info("Succeeded: %d", succeeded)
    logger.info("Failed: %d", failed)
    logger.info("Total rows loaded: %d", total_rows)
    logger.info("Elapsed: %.1fs", time.time() - start_all)

    for table, row_count in summary_report(conn, config.sql_schema):
        logger.info("  %s: %d rows", table, row_count)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = build_config(argv)
    conn = connect(config)
    try:
        run(config, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

`README.md`:
```markdown
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_migrate_csv.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest -v`
Expected: all 27 tests pass (7 from Task 2 + 10 from Task 3 + 3 from Task 4 + 4 from Task 5 + 3 from Task 6). If the count differs, that's fine as long as every test passes and none was silently skipped or errored.

- [ ] **Step 6: Commit**

```bash
git add migrate_csv.py README.md tests/test_migrate_csv.py
git commit -m "feat: add orchestration script and usage docs"
```

---

## Manual verification (not automated)

The DB load path (`connect`, and the real behavior of `create_table`/`load_rows`/`summary_report` against a live server) is only exercised in tests via mocks, per the design spec's testing section. Before relying on this script against real data:

1. Point `migrate.env` at a real (ideally non-production/staging) SQL Server and a throwaway folder with 2-3 real CSVs, including at least one with a comma or newline inside a quoted field.
2. Run `python migrate_csv.py` and confirm: tables are created, row counts in the summary match `wc -l` (minus 1 for header) on each source file, and the quoted-field values landed intact (spot-check with a `SELECT`).
3. Re-run the same command and confirm tables are dropped and recreated cleanly (no duplicate-table errors, no leftover rows from the previous run).

If no SQL Server is reachable to test against right now, say so explicitly rather than claiming the load path works.
