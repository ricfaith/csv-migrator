import csv
import logging
import sys


def _configure_field_size_limit():
    try:
        csv.field_size_limit(sys.maxsize)
    except OverflowError:
        csv.field_size_limit(2**31 - 1)


_configure_field_size_limit()

logger = logging.getLogger(__name__)


def open_csv_reader(path):
    try:
        f = open(path, "r", encoding="utf-8-sig", newline="")
        while f.read(65536):
            pass
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
