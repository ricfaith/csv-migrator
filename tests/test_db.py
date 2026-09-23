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
