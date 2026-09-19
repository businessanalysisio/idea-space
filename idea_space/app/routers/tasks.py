from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Label, Task
from app.routers import calendar as calendar_router
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


def _filtered_tasks(db: Session, label_ids: list[int] | None, status: str) -> list[Task]:
    query = db.query(Task).filter(Task.status == status)
    if label_ids:
        query = query.join(Task.labels).filter(Label.id.in_(label_ids)).distinct()
    tasks = query.order_by(Task.due_date.asc()).all()
    return _attach_overdue_flag(tasks)


def _open_tasks(db: Session) -> list[Task]:
    return _filtered_tasks(db, None, "open")


@router.get("/tasks")
def list_tasks(
    request: Request,
    labels: str | None = None,
    status: str = "open",
    db: Session = Depends(get_db),
):
    label_ids = [int(x) for x in labels.split(",")] if labels else None
    tasks = _filtered_tasks(db, label_ids, status)
    all_labels = db.query(Label).order_by(Label.name.asc()).all()
    return templates.TemplateResponse(
        request,
        "tasks/list.html",
        {
            "tasks": tasks,
            "all_labels": all_labels,
            "selected_label_ids": label_ids or [],
            "status": status,
        },
    )


@router.post("/tasks")
def create_task(
    request: Request,
    title: str = Form(...),
    due_date: str = Form(...),
    recurrence_pattern: str | None = Form(None),
    recurrence_interval: int = Form(1),
    recurrence_days_of_week: str | None = Form(None),
    remind_at: str | None = Form(None),
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

    if remind_at:
        from app.models import Reminder

        parsed_remind_at = datetime.fromisoformat(remind_at).replace(tzinfo=timezone.utc)
        db.add(Reminder(task_id=task.id, remind_at=parsed_remind_at))
        db.commit()

    if recurrence_pattern:
        task.recurrence_series_id = task.id
        db.commit()

    tasks = _open_tasks(db)
    all_labels = db.query(Label).order_by(Label.name.asc()).all()
    return templates.TemplateResponse(
        request,
        "tasks/_task_list_only.html",
        {"tasks": tasks, "all_labels": all_labels},
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
                labels=list(task.labels),
            )
            db.add(successor)
            db.commit()

    tasks = _open_tasks(db)
    all_labels = db.query(Label).order_by(Label.name.asc()).all()
    return templates.TemplateResponse(
        request,
        "tasks/_task_list_only.html",
        {"tasks": tasks, "all_labels": all_labels},
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
    all_labels = db.query(Label).order_by(Label.name.asc()).all()
    return templates.TemplateResponse(
        request,
        "tasks/_task_list_only.html",
        {"tasks": tasks, "all_labels": all_labels},
    )


@router.patch("/tasks/{task_id}/reschedule")
def reschedule_task(
    request: Request,
    task_id: int,
    due_date: str = Form(...),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if task is None or task.status != "open":
        raise HTTPException(status_code=404, detail="Task not found")

    new_date = datetime.strptime(due_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    task.due_date = task.due_date.replace(
        year=new_date.year, month=new_date.month, day=new_date.day
    )
    db.commit()

    return calendar_router.calendar_week(request, start=None, db=db)
