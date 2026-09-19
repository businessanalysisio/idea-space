from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Task
from app.seed import seed_default_workspace
from app.services.recurrence import compute_next_due_date

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


@router.post("/tasks/{task_id}/complete")
def complete_task(request: Request, task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = "done"
    task.completed_at = datetime.now(timezone.utc)
    db.commit()

    if task.recurrence_active:
        # SQLite strips tzinfo on read-back; normalize before using in compute_next_due_date
        if task.due_date.tzinfo is None:
            task.due_date = task.due_date.replace(tzinfo=timezone.utc)

        next_due = compute_next_due_date(
            task.recurrence_pattern,
            task.recurrence_interval,
            task.recurrence_days_of_week,
            task.due_date,
        )
        if next_due is not None:
            successor = Task(
                workspace_id=task.workspace_id,
                owner_id=task.owner_id,
                title=task.title,
                description=task.description,
                due_date=next_due,
                recurrence_series_id=task.recurrence_series_id,
                recurrence_pattern=task.recurrence_pattern,
                recurrence_interval=task.recurrence_interval,
                recurrence_days_of_week=task.recurrence_days_of_week,
                recurrence_active=True,
            )
            db.add(successor)
            db.commit()

    tasks = _open_tasks(db)
    return templates.TemplateResponse(
        request, "tasks/list.html", {"tasks": tasks}
    )


@router.patch("/tasks/{task_id}/recurrence")
def set_recurrence_active(
    request: Request,
    task_id: int,
    active: str = Form(...),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if task is None or task.recurrence_pattern is None:
        raise HTTPException(status_code=404, detail="Recurring task not found")

    task.recurrence_active = active.lower() == "true"
    db.commit()

    tasks = _open_tasks(db)
    return templates.TemplateResponse(
        request, "tasks/list.html", {"tasks": tasks}
    )
