from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.db import Base, SessionLocal, engine
from app.routers import calendar, decisions, labels, reminders, requirements, risks, stakeholders, tasks
from app.seed import seed_default_workspace

app = FastAPI(title="Idea Space")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(tasks.router)
app.include_router(labels.router)
app.include_router(calendar.router)
app.include_router(reminders.router)
app.include_router(stakeholders.router)
app.include_router(decisions.router)
app.include_router(risks.router)
app.include_router(requirements.router)


def ensure_completion_note_column(target_engine) -> None:
    """Idempotently add tasks.completion_note to a pre-existing (Slice 1) database.

    `Base.metadata.create_all` only creates missing tables; it never adds
    columns to a table that already exists. Any database created before this
    slice already has a `tasks` table without `completion_note`, so we patch
    it in directly.
    """
    with target_engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(tasks)"))}
        if "completion_note" not in columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN completion_note TEXT"))
            conn.commit()


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    ensure_completion_note_column(engine)
    db = SessionLocal()
    try:
        seed_default_workspace(db)
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}
