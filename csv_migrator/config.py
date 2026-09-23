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
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if " #" in value:
                value = value.split(" #", 1)[0].rstrip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            values[key] = value
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
