import sys
from unittest.mock import MagicMock

from csv_migrator.config import Config
from csv_migrator.db import (
    quote_identifier,
    create_table,
    load_rows,
    escape_odbc_value,
    connect,
)


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


def test_create_table_handles_special_characters_in_table_name():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    create_table(conn, "dbo", "O'Brien_Orders", ["Col_A"])
    drop_sql = cursor.execute.call_args_list[0].args[0]
    assert drop_sql == "DROP TABLE IF EXISTS [dbo].[O'Brien_Orders]"


def test_load_rows_batches_and_returns_total_count():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    rows = [["a", "1"], ["b", "2"], ["c", "3"]]

    total = load_rows(conn, "dbo", "MyTable", ["Col_A", "Col_B"], iter(rows), batch_size=2)

    assert total == 3
    assert cursor.executemany.call_count == 2
    assert cursor.fast_executemany is True


def test_escape_odbc_value_wraps_and_doubles_braces():
    assert escape_odbc_value("simple") == "{simple}"
    assert escape_odbc_value("has;semi") == "{has;semi}"
    assert escape_odbc_value("has}brace") == "{has}}brace}"


def test_connect_builds_escaped_connection_string(monkeypatch):
    fake_pyodbc = MagicMock()
    monkeypatch.setitem(sys.modules, "pyodbc", fake_pyodbc)

    config = Config(
        csv_folder="/data",
        sql_server="host;withsemicolon",
        sql_database="db",
        sql_schema="dbo",
        sql_user="user",
        sql_password="p@ss}word",
    )

    connect(config)

    conn_str = fake_pyodbc.connect.call_args.args[0]
    assert "{host;withsemicolon}" in conn_str
    assert "{p@ss}}word}" in conn_str
