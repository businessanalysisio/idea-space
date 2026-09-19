from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Task
from app.services.recurrence import project_occurrences

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _week_start(start_param: str | None) -> datetime:
    if start_param:
        day = datetime.strptime(start_param, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        today = datetime.now(timezone.utc)
        day = today - timedelta(days=today.weekday())
    return day.replace(hour=0, minute=0, second=0, microsecond=0)


@router.get("/calendar")
def calendar_week(request: Request, start: str | None = None, db: Session = Depends(get_db)):
    week_start = _week_start(start)
    week_end = week_start + timedelta(days=7)
    now = datetime.now(timezone.utc)

    open_tasks = db.query(Task).filter(Task.status == "open").all()

    # SQLite strips tzinfo on read-back; normalize before comparing.
    for t in open_tasks:
        if t.due_date.tzinfo is None:
            t.due_date = t.due_date.replace(tzinfo=timezone.utc)

    overdue = [t for t in open_tasks if t.due_date < week_start and t.due_date < now]

    days = []
    for offset in range(7):
        day_start = week_start + timedelta(days=offset)
        day_end = day_start + timedelta(days=1)

        real_items = [
            {"title": t.title, "due_date": t.due_date, "virtual": False, "id": t.id}
            for t in open_tasks
            if day_start <= t.due_date < day_end
        ]

        virtual_items = []
        for t in open_tasks:
            if not t.recurrence_active or t.due_date >= day_end:
                continue
            occurrences = project_occurrences(
                t.recurrence_pattern,
                t.recurrence_interval,
                t.recurrence_days_of_week,
                t.due_date,
                day_start,
                day_end,
            )
            for occ in occurrences:
                virtual_items.append({"title": t.title, "due_date": occ, "virtual": True})

        days.append({"date": day_start, "items": real_items + virtual_items})

    return templates.TemplateResponse(
        request,
        "calendar/week.html",
        {"days": days, "overdue": overdue, "week_start": week_start},
    )
