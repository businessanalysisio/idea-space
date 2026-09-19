from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import Base, SessionLocal, engine
from app.routers import calendar, labels, reminders, tasks
from app.seed import seed_default_workspace

app = FastAPI(title="Idea Space")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(tasks.router)
app.include_router(labels.router)
app.include_router(calendar.router)
app.include_router(reminders.router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_default_workspace(db)
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}
