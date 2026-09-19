from fastapi import FastAPI

from app.db import Base, SessionLocal, engine
from app.seed import seed_default_workspace

app = FastAPI(title="Idea Space")


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
