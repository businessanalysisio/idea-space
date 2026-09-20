from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ActivityLog, Label, Task
from app.routers import calendar as calendar_router
from app.seed import seed_default_workspace
from app.services.activity import record_change
from app.services.recurrence import compute_next_due_date

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

VALID_STATUSES = {"open", "done", "archived"}


def _normalize_due_date(task: Task) -> None:
    # SQLite strips tzinfo on read-back; normalize before comparing.
    if task.due_date.tzinfo is None:
        task.due_date = task.due_date.replace(tzinfo=timezone.utc)


def _attach_overdue_flag(tasks: list[Task]) -> list[Task]:
    now = datetime.now(timezone.utc)
    for task in tasks:
        _normalize_due_date(task)
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


def _board_columns(open_tasks: list[Task], done_tasks: list[Task]) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    now_column = [t for t in open_tasks if t.due_date < today_end]
    next_column = [t for t in open_tasks if t.due_date >= today_end]
    done_column = sorted(
        done_tasks, key=lambda t: t.completed_at or t.created_at, reverse=True
    )[:10]

    return {"now": now_column, "next": next_column, "done": done_column, "today_start": today_start, "today_end": today_end}


def _task_metrics(db: Session, label_ids: list[int] | None = None) -> dict:
    open_query = db.query(Task).filter(Task.status == "open")
    done_query = db.query(Task).filter(Task.status == "done")
    if label_ids:
        open_query = open_query.join(Task.labels).filter(Label.id.in_(label_ids)).distinct()
        done_query = done_query.join(Task.labels).filter(Label.id.in_(label_ids)).distinct()

    open_tasks = _attach_overdue_flag(open_query.all())
    done_tasks = done_query.all()

    columns = _board_columns(open_tasks, done_tasks)

    open_count = len(open_tasks)
    in_focus_count = len(
        [t for t in open_tasks if columns["today_start"] <= t.due_date < columns["today_end"]]
    )
    completed_count = len(done_tasks)
    velocity = (
        round(completed_count / (completed_count + open_count) * 100)
        if (completed_count + open_count) > 0
        else 0
    )
    blocked_count = db.query(Task).filter(Task.blocked.is_(True)).count()

    return {
        "open_count": open_count,
        "in_focus_count": in_focus_count,
        "completed_count": completed_count,
        "velocity": velocity,
        "blocked_count": blocked_count,
        "columns": columns,
    }


def _render_task_board(request: Request, db: Session, label_ids: list[int] | None = None):
    metrics = _task_metrics(db, label_ids)
    all_labels = db.query(Label).order_by(Label.name.asc()).all()
    return templates.TemplateResponse(
        request,
        "tasks/_board.html",
        {
            "columns": metrics["columns"],
            "open_count": metrics["open_count"],
            "in_focus_count": metrics["in_focus_count"],
            "completed_count": metrics["completed_count"],
            "velocity": metrics["velocity"],
            "blocked_count": metrics["blocked_count"],
            "all_labels": all_labels,
            "selected_label_ids": label_ids or [],
        },
    )


@router.get("/tasks")
def list_tasks(
    request: Request,
    labels: str | None = None,
    status: str = "open",
    db: Session = Depends(get_db),
):
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    all_labels = db.query(Label).order_by(Label.name.asc()).all()
    label_ids = [int(x) for x in labels.split(",")] if labels else None

    if status == "archived":
        tasks = _filtered_tasks(db, label_ids, "archived")
        return templates.TemplateResponse(
            request,
            "tasks/list.html",
            {
                "show_archived": True,
                "tasks": tasks,
                "all_labels": all_labels,
                "selected_label_ids": label_ids or [],
                "active_nav": "tasks",
            },
        )

    metrics = _task_metrics(db, label_ids)
    return templates.TemplateResponse(
        request,
        "tasks/list.html",
        {
            "show_archived": False,
            "columns": metrics["columns"],
            "open_count": metrics["open_count"],
            "in_focus_count": metrics["in_focus_count"],
            "completed_count": metrics["completed_count"],
            "velocity": metrics["velocity"],
            "blocked_count": metrics["blocked_count"],
            "all_labels": all_labels,
            "selected_label_ids": label_ids or [],
            "active_nav": "tasks",
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

    return _render_task_board(request, db)


@router.post("/tasks/{task_id}/complete")
def complete_task(
    request: Request,
    task_id: int,
    completion_note: str | None = Form(None),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if task is None or task.status != "open":
        raise HTTPException(status_code=404, detail="Task not found or not open")

    record_change(db, task, "status", task.status, "done")
    task.status = "done"
    task.completed_at = datetime.now(timezone.utc)
    task.completion_note = completion_note or None
    db.commit()

    if task.recurrence_active:
        _normalize_due_date(task)

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

    return _render_task_board(request, db)


@router.post("/tasks/{task_id}/archive")
def archive_task(request: Request, task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None or task.status != "done":
        raise HTTPException(status_code=404, detail="Task not found or not done")

    record_change(db, task, "status", "done", "archived")
    task.status = "archived"
    db.commit()

    return _render_task_board(request, db)


@router.get("/tasks/{task_id}/history")
def task_history(request: Request, task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    entries = (
        db.query(ActivityLog)
        .filter(ActivityLog.task_id == task_id)
        .order_by(ActivityLog.changed_at.desc(), ActivityLog.id.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "tasks/_history.html",
        {"task_id": task_id, "entries": entries, "completion_note": task.completion_note},
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

    return _render_task_board(request, db)


@router.patch("/tasks/{task_id}/block")
def toggle_blocked(request: Request, task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None or task.status == "archived":
        raise HTTPException(status_code=404, detail="Task not found")

    task.blocked = not task.blocked
    db.commit()

    return _render_task_board(request, db)


@router.patch("/tasks/{task_id}/reschedule")
def reschedule_task(
    request: Request,
    task_id: int,
    due_date: str = Form(...),
    view: str = Form("month"),
    month: str | None = Form(None),
    start: str | None = Form(None),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if task is None or task.status != "open":
        raise HTTPException(status_code=404, detail="Task not found")

    old_date_str = task.due_date.strftime("%Y-%m-%d")
    new_date = datetime.strptime(due_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    task.due_date = task.due_date.replace(
        year=new_date.year, month=new_date.month, day=new_date.day
    )
    record_change(db, task, "due_date", old_date_str, due_date)
    db.commit()

    return calendar_router.render_calendar(request, db, view=view, month=month, start=start)
