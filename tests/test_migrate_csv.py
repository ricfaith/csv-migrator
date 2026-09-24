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
    assert conn.rollback.call_count == 1
    assert "good.csv: starting (2 rows)" in caplog.text
    assert "  good: 2 rows" in caplog.text
    assert "  bad:" not in caplog.text


def test_run_skips_file_with_colliding_table_name(tmp_path, caplog, monkeypatch):
    (tmp_path / "foo-bar.csv").write_text("X,Y\n1,2\n")
    (tmp_path / "foo_bar.csv").write_text("X,Y\n3,4\n")

    import migrate_csv

    monkeypatch.setattr(migrate_csv, "create_table", lambda *a, **k: None)
    monkeypatch.setattr(migrate_csv, "load_rows", lambda *a, **k: 1)

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
        failed = run(config, conn)

    assert failed == 1
    assert "collides" in caplog.text
