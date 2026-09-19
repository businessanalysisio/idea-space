from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Reminder, Task

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _due_reminders(db: Session) -> list[Reminder]:
    now = datetime.now(timezone.utc)
    reminders = (
        db.query(Reminder)
        .join(Task, Reminder.task_id == Task.id)
        .filter(
            Reminder.remind_at <= now,
            Reminder.dismissed_at.is_(None),
            Task.status == "open",
        )
        .all()
    )
    due = []
    for r in reminders:
        # SQLite strips tzinfo on read-back; normalize before comparing
        if r.snoozed_until is not None and r.snoozed_until.tzinfo is None:
            r.snoozed_until = r.snoozed_until.replace(tzinfo=timezone.utc)

        if r.snoozed_until is None or r.snoozed_until <= now:
            r.task_title = r.task.title
            due.append(r)

    return due


@router.get("/reminders/due")
def due_reminders(request: Request, db: Session = Depends(get_db)):
    reminders = _due_reminders(db)
    return templates.TemplateResponse(
        request, "reminders/_banner.html", {"reminders": reminders}
    )


@router.post("/reminders/{reminder_id}/dismiss")
def dismiss_reminder(request: Request, reminder_id: int, db: Session = Depends(get_db)):
    reminder = db.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    reminder.dismissed_at = datetime.now(timezone.utc)
    db.commit()

    return templates.TemplateResponse(
        request, "reminders/_banner.html", {"reminders": _due_reminders(db)}
    )


@router.post("/reminders/{reminder_id}/snooze")
def snooze_reminder(
    request: Request, reminder_id: int, minutes: int = Form(15), db: Session = Depends(get_db)
):
    reminder = db.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    reminder.snoozed_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    db.commit()

    return templates.TemplateResponse(
        request, "reminders/_banner.html", {"reminders": _due_reminders(db)}
    )
