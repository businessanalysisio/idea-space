from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Task
from app.seed import seed_default_workspace

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _attach_overdue_flag(tasks: list[Task]) -> list[Task]:
    now = datetime.now(timezone.utc)
    for task in tasks:
        # SQLite strips tzinfo on read-back; normalize before comparing.
        if task.due_date.tzinfo is None:
            task.due_date = task.due_date.replace(tzinfo=timezone.utc)
        task.is_overdue = task.status == "open" and task.due_date < now
    return tasks


def _open_tasks(db: Session) -> list[Task]:
    tasks = (
        db.query(Task)
        .filter(Task.status == "open")
        .order_by(Task.due_date.asc())
        .all()
    )
    return _attach_overdue_flag(tasks)


@router.get("/tasks")
def list_tasks(request: Request, db: Session = Depends(get_db)):
    tasks = _open_tasks(db)
    return templates.TemplateResponse(
        request, "tasks/list.html", {"tasks": tasks}
    )


@router.post("/tasks")
def create_task(
    request: Request,
    title: str = Form(...),
    due_date: str = Form(...),
    recurrence_pattern: str | None = Form(None),
    recurrence_interval: int = Form(1),
    recurrence_days_of_week: str | None = Form(None),
    db: Session = Depends(get_db),
):
    workspace, user = seed_default_workspace(db)
    parsed_due = datetime.fromisoformat(due_date).replace(tzinfo=timezone.utc)

    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title=title,
        due_date=parsed_due,
        recurrence_pattern=recurrence_pattern or None,
        recurrence_interval=recurrence_interval,
        recurrence_days_of_week=recurrence_days_of_week or None,
        recurrence_active=bool(recurrence_pattern),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    if recurrence_pattern:
        task.recurrence_series_id = task.id
        db.commit()

    tasks = _open_tasks(db)
    return templates.TemplateResponse(
        request, "tasks/list.html", {"tasks": tasks}
    )
