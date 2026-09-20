import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase


def normalize_database_url(url: str) -> str:
    """Rewrite a Postgres URL to use this app's driver.

    Vercel Postgres / most Postgres providers hand out "postgres://" or
    plain "postgresql://" URLs, which SQLAlchemy resolves to the psycopg2
    driver by default. This app uses psycopg (v3) instead, so both
    schemes are rewritten to the explicit "postgresql+psycopg://" driver.
    A URL that already names a driver is left unchanged.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    engine = create_engine(normalize_database_url(DATABASE_URL), pool_pre_ping=True)
else:
    DB_PATH = os.environ.get("IDEA_SPACE_DB", "idea_space.db")
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
