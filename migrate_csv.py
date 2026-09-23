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
        return 0

    succeeded = 0
    failed = 0
    total_rows = 0
    start_all = time.time()
    seen_tables = {}

    for path in csv_files:
        filename = os.path.basename(path)
        table_name = table_name_from_filename(filename)
        if table_name.lower() in seen_tables:
            failed += 1
            logger.error(
                "%s: FAILED - table name '%s' collides with already-processed file %s",
                filename, table_name, seen_tables[table_name.lower()],
            )
            continue
        seen_tables[table_name.lower()] = filename

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
            conn.rollback()
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

    return failed


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = build_config(argv)
    conn = connect(config)
    try:
        failed = run(config, conn)
    finally:
        conn.close()
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
