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
