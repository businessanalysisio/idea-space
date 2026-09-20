from app.db import normalize_database_url


def test_postgres_scheme_is_rewritten_to_psycopg_driver():
    result = normalize_database_url("postgres://user:pass@example.com:5432/idea_space")
    assert result == "postgresql+psycopg://user:pass@example.com:5432/idea_space"


def test_postgresql_scheme_is_rewritten_to_psycopg_driver():
    result = normalize_database_url("postgresql://user:pass@example.com:5432/idea_space")
    assert result == "postgresql+psycopg://user:pass@example.com:5432/idea_space"


def test_explicit_psycopg_driver_is_left_unchanged():
    url = "postgresql+psycopg://user:pass@example.com:5432/idea_space"
    assert normalize_database_url(url) == url


def test_sqlite_url_is_left_unchanged():
    url = "sqlite:///idea_space.db"
    assert normalize_database_url(url) == url
