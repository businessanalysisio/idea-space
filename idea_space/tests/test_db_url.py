import importlib
import sys


def _reload_db_module(monkeypatch, database_url):
    if database_url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", database_url)

    sys.modules.pop("app.db", None)
    return importlib.import_module("app.db")


def test_no_database_url_falls_back_to_sqlite(monkeypatch):
    db_module = _reload_db_module(monkeypatch, None)
    try:
        assert db_module.engine.dialect.name == "sqlite"
    finally:
        sys.modules.pop("app.db", None)


def test_postgres_scheme_is_rewritten_to_psycopg_driver(monkeypatch):
    db_module = _reload_db_module(
        monkeypatch, "postgres://user:pass@example.com:5432/idea_space"
    )
    try:
        assert str(db_module.engine.url).startswith("postgresql+psycopg://")
    finally:
        sys.modules.pop("app.db", None)


def test_postgresql_scheme_is_rewritten_to_psycopg_driver(monkeypatch):
    db_module = _reload_db_module(
        monkeypatch, "postgresql://user:pass@example.com:5432/idea_space"
    )
    try:
        assert str(db_module.engine.url).startswith("postgresql+psycopg://")
    finally:
        sys.modules.pop("app.db", None)


def test_explicit_psycopg_driver_is_left_unchanged(monkeypatch):
    db_module = _reload_db_module(
        monkeypatch, "postgresql+psycopg://user:pass@example.com:5432/idea_space"
    )
    try:
        assert str(db_module.engine.url).startswith("postgresql+psycopg://")
    finally:
        sys.modules.pop("app.db", None)
