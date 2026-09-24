def escape_odbc_value(value):
    return "{" + str(value).replace("}", "}}") + "}"


def connect(config):
    import pyodbc

    conn_str = (
        f"DRIVER={escape_odbc_value(config.sql_driver)};"
        f"SERVER={escape_odbc_value(config.sql_server)};"
        f"DATABASE={escape_odbc_value(config.sql_database)};"
        f"UID={escape_odbc_value(config.sql_user)};"
        f"PWD={escape_odbc_value(config.sql_password)};"
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
    cursor.execute(f"DROP TABLE IF EXISTS {qualified}")
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
