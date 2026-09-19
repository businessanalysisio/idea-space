from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Label, Task, TaskLabel
from app.seed import seed_default_workspace

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _all_labels(db: Session) -> list[Label]:
    return db.query(Label).order_by(Label.name.asc()).all()


@router.post("/labels")
def create_label(
    request: Request, name: str = Form(...), color: str = Form("#6b7280"), db: Session = Depends(get_db)
):
    workspace, _ = seed_default_workspace(db)
    label = Label(workspace_id=workspace.id, name=name, color=color)
    db.add(label)
    db.commit()

    return templates.TemplateResponse(
        request, "labels/_filter_bar.html", {"all_labels": _all_labels(db)}
    )


@router.patch("/labels/{label_id}")
def rename_label(request: Request, label_id: int, name: str = Form(...), db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found")

    label.name = name
    db.commit()

    return templates.TemplateResponse(
        request, "labels/_filter_bar.html", {"all_labels": _all_labels(db)}
    )


@router.delete("/labels/{label_id}")
def delete_label(request: Request, label_id: int, db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found")

    db.query(TaskLabel).filter(TaskLabel.label_id == label_id).delete()
    db.delete(label)
    db.commit()

    return templates.TemplateResponse(
        request, "labels/_filter_bar.html", {"all_labels": _all_labels(db)}
    )


@router.post("/tasks/{task_id}/labels")
def assign_label(
    request: Request, task_id: int, label_id: int = Form(...), db: Session = Depends(get_db)
):
    task = db.get(Task, task_id)
    label = db.get(Label, label_id)
    if task is None or label is None:
        raise HTTPException(status_code=404, detail="Task or label not found")

    if label not in task.labels:
        task.labels.append(label)
        db.commit()

    from app.routers.tasks import _open_tasks

    tasks = _open_tasks(db)
    all_labels = _all_labels(db)
    return templates.TemplateResponse(
        request,
        "tasks/list.html",
        {"tasks": tasks, "all_labels": all_labels, "selected_label_ids": [], "status": "open"},
    )
