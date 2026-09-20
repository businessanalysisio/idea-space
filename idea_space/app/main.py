from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.db import Base, SessionLocal, engine
from app.middleware import SitePasswordMiddleware
from app.routers import calendar, decisions, labels, matrix, reminders, requirements, risks, stakeholders, tasks
from app.seed import seed_default_workspace

app = FastAPI(title="Idea Space")
app.add_middleware(SitePasswordMiddleware)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(tasks.router)
app.include_router(labels.router)
app.include_router(calendar.router)
app.include_router(reminders.router)
app.include_router(stakeholders.router)
app.include_router(decisions.router)
app.include_router(risks.router)
app.include_router(requirements.router)
app.include_router(matrix.router)


def ensure_completion_note_column(target_engine) -> None:
    """Idempotently add tasks.completion_note to a pre-existing (Slice 1) database.

    `Base.metadata.create_all` only creates missing tables; it never adds
    columns to a table that already exists. Any database created before this
    slice already has a `tasks` table without `completion_note`, so we patch
    it in directly.

    Uses SQLite's `PRAGMA table_info`, so this only applies to SQLite targets
    (the local/default database). A freshly provisioned Postgres database has
    no pre-existing rows to migrate from — `create_all` alone gives it every
    column the current models define.
    """
    if target_engine.dialect.name != "sqlite":
        return

    with target_engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(tasks)"))}
        if "completion_note" not in columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN completion_note TEXT"))
            conn.commit()


def ensure_redesign_columns(target_engine) -> None:
    """Idempotently add tasks.blocked and requirements.updated_at to a
    pre-existing (pre-redesign) database.

    Same rationale as ensure_completion_note_column: create_all never adds
    columns to a table that already exists, so a database created before
    this redesign needs these two columns patched in directly. SQLite-only
    for the same reason — see ensure_completion_note_column.
    """
    if target_engine.dialect.name != "sqlite":
        return

    with target_engine.connect() as conn:
        task_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(tasks)"))}
        if "blocked" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN blocked BOOLEAN DEFAULT 0"))
            conn.commit()

        requirement_columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(requirements)"))
        }
        if "updated_at" not in requirement_columns:
            conn.execute(text("ALTER TABLE requirements ADD COLUMN updated_at DATETIME"))
            conn.execute(
                text("UPDATE requirements SET updated_at = created_at WHERE updated_at IS NULL")
            )
            conn.commit()


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    ensure_completion_note_column(engine)
    ensure_redesign_columns(engine)
    db = SessionLocal()
    try:
        seed_default_workspace(db)
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}
