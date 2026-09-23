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
