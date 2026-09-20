from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import RequirementStakeholder, Stakeholder
from app.seed import seed_default_workspace

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _all_stakeholders(db: Session) -> list[Stakeholder]:
    return db.query(Stakeholder).order_by(Stakeholder.name.asc()).all()


@router.post("/stakeholders")
def create_stakeholder(
    request: Request,
    name: str = Form(...),
    role: str = Form(...),
    contact_info: str | None = Form(None),
    db: Session = Depends(get_db),
):
    workspace, _ = seed_default_workspace(db)
    stakeholder = Stakeholder(
        workspace_id=workspace.id, name=name, role=role, contact_info=contact_info or None
    )
    db.add(stakeholder)
    db.commit()

    return templates.TemplateResponse(
        request, "stakeholders/_manager.html", {"all_stakeholders": _all_stakeholders(db)}
    )


@router.patch("/stakeholders/{stakeholder_id}")
def edit_stakeholder(
    request: Request,
    stakeholder_id: int,
    name: str = Form(...),
    role: str = Form(...),
    contact_info: str | None = Form(None),
    db: Session = Depends(get_db),
):
    stakeholder = db.get(Stakeholder, stakeholder_id)
    if stakeholder is None:
        raise HTTPException(status_code=404, detail="Stakeholder not found")

    stakeholder.name = name
    stakeholder.role = role
    stakeholder.contact_info = contact_info or None
    db.commit()

    return templates.TemplateResponse(
        request, "stakeholders/_manager.html", {"all_stakeholders": _all_stakeholders(db)}
    )


@router.delete("/stakeholders/{stakeholder_id}")
def delete_stakeholder(request: Request, stakeholder_id: int, db: Session = Depends(get_db)):
    stakeholder = db.get(Stakeholder, stakeholder_id)
    if stakeholder is None:
        raise HTTPException(status_code=404, detail="Stakeholder not found")

    db.query(RequirementStakeholder).filter(
        RequirementStakeholder.stakeholder_id == stakeholder_id
    ).delete()
    db.delete(stakeholder)
    db.commit()

    return templates.TemplateResponse(
        request, "stakeholders/_manager.html", {"all_stakeholders": _all_stakeholders(db)}
    )
