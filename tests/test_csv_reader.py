import os
import sys

from csv_migrator.csv_reader import count_data_rows, read_header_and_rows, validated_rows

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


def test_count_data_rows_excludes_header():
    path = os.path.join(FIXTURES_DIR, "quoted_fields.csv")
    assert count_data_rows(path) == 2


def test_late_non_utf8_byte_falls_back_to_latin1(tmp_path):
    path = tmp_path / "late_encoding.csv"
    padding = "A" * 70000
    content = f"Name,Notes\n{padding},ok\nLast,caf\xe9\n"
    path.write_bytes(content.encode("latin-1"))

    f, header, reader = read_header_and_rows(str(path))
    try:
        rows = list(reader)
    finally:
        f.close()

    assert header == ["Name", "Notes"]
    assert rows[-1] == ["Last", "caf\xe9"]


def test_large_field_does_not_raise(tmp_path):
    path = tmp_path / "big_field.csv"
    big_value = "x" * 200000
    path.write_text(f"Name,Notes\nA,{big_value}\n")

    f, header, reader = read_header_and_rows(str(path))
    try:
        rows = list(reader)
    finally:
        f.close()

    assert len(rows[0][1]) == 200000


def test_field_size_limit_falls_back_on_overflow(monkeypatch):
    import csv as csv_module
    from csv_migrator import csv_reader

    calls = []

    def fake_limit(value):
        calls.append(value)
        if value == sys.maxsize:
            raise OverflowError("simulated")

    monkeypatch.setattr(csv_module, "field_size_limit", fake_limit)
    csv_reader._configure_field_size_limit()
    assert calls[-1] == 2**31 - 1
