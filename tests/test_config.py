import getpass as getpass_module

import pytest

from csv_migrator.config import parse_env_file, resolve_value, resolve_password, build_config

_ALL_KEYS = ["CSV_FOLDER", "SQL_SERVER", "SQL_DATABASE", "SQL_SCHEMA", "SQL_USER", "SQL_PASSWORD"]


def _clear_env(monkeypatch):
    for key in _ALL_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_parse_env_file_skips_comments_and_blank_lines(tmp_path):
    env_path = tmp_path / "migrate.env"
    env_path.write_text(
        "# comment\n"
        "\n"
        "CSV_FOLDER=/data/csvs\n"
        "SQL_SERVER = myhost \n"
    )
    values = parse_env_file(str(env_path))
    assert values == {"CSV_FOLDER": "/data/csvs", "SQL_SERVER": "myhost"}


def test_parse_env_file_missing_file_returns_empty_dict(tmp_path):
    assert parse_env_file(str(tmp_path / "nope.env")) == {}


def test_parse_env_file_strips_inline_comments(tmp_path):
    env_path = tmp_path / "migrate.env"
    env_path.write_text("SQL_SCHEMA=dbo  # default schema\n")
    values = parse_env_file(str(env_path))
    assert values == {"SQL_SCHEMA": "dbo"}


def test_parse_env_file_strips_surrounding_quotes(tmp_path):
    env_path = tmp_path / "migrate.env"
    env_path.write_text('CSV_FOLDER="/path/with spaces"\n')
    values = parse_env_file(str(env_path))
    assert values == {"CSV_FOLDER": "/path/with spaces"}


def test_parse_env_file_quoted_value_containing_hash_is_not_truncated(tmp_path):
    env_path = tmp_path / "migrate.env"
    env_path.write_text('SQL_PASSWORD="p@ss #1"\n')
    values = parse_env_file(str(env_path))
    assert values == {"SQL_PASSWORD": "p@ss #1"}


def test_parse_env_file_handles_utf8_bom(tmp_path):
    env_path = tmp_path / "migrate.env"
    env_path.write_bytes("﻿CSV_FOLDER=/data\n".encode("utf-8"))
    values = parse_env_file(str(env_path))
    assert values == {"CSV_FOLDER": "/data"}


def test_resolve_value_precedence_cli_wins(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SQL_SERVER", "env-host")
    result = resolve_value("sql_server", "cli-host", {"SQL_SERVER": "file-host"})
    assert result == "cli-host"


def test_resolve_value_precedence_env_var_over_file(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SQL_SERVER", "env-host")
    result = resolve_value("sql_server", None, {"SQL_SERVER": "file-host"})
    assert result == "env-host"


def test_resolve_value_precedence_file_over_default(monkeypatch):
    _clear_env(monkeypatch)
    result = resolve_value("sql_server", None, {"SQL_SERVER": "file-host"}, default="fallback")
    assert result == "file-host"


def test_resolve_value_falls_back_to_default(monkeypatch):
    _clear_env(monkeypatch)
    result = resolve_value("sql_schema", None, {}, default="dbo")
    assert result == "dbo"


def test_resolve_password_falls_back_to_file_value(monkeypatch):
    _clear_env(monkeypatch)
    result = resolve_password({"SQL_PASSWORD": "file-secret"})
    assert result == "file-secret"


def test_resolve_password_prompts_when_not_set(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr(getpass_module, "getpass", lambda prompt="": "typed-secret")
    result = resolve_password({})
    assert result == "typed-secret"


def test_build_config_raises_on_missing_required(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    empty_env = tmp_path / "migrate.env"
    empty_env.write_text("")
    with pytest.raises(SystemExit):
        build_config(["--env-file", str(empty_env)])


def test_build_config_resolves_from_env_file(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    env_path = tmp_path / "migrate.env"
    env_path.write_text(
        "CSV_FOLDER=/data\nSQL_SERVER=host\nSQL_DATABASE=Staging1\nSQL_USER=me\nSQL_PASSWORD=secret\n"
    )
    config = build_config(["--env-file", str(env_path)])
    assert config.csv_folder == "/data"
    assert config.sql_server == "host"
    assert config.sql_database == "Staging1"
    assert config.sql_schema == "dbo"
    assert config.sql_user == "me"
    assert config.sql_password == "secret"
