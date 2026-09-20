from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Decision,
    Requirement,
    RequirementDecision,
    RequirementRisk,
    RequirementStakeholder,
    RequirementTask,
    Risk,
    Stakeholder,
    Task,
)
from app.seed import seed_default_workspace

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

VALID_REQUIREMENT_STATUSES = {"draft", "approved", "in_progress", "delivered"}


def _all_requirements(db: Session) -> list[Requirement]:
    return db.query(Requirement).order_by(Requirement.created_at.desc()).all()


def _requirement_page_context(db: Session, requirement: Requirement) -> dict:
    return {
        "requirement": requirement,
        "all_stakeholders": db.query(Stakeholder).order_by(Stakeholder.name.asc()).all(),
        "all_decisions": db.query(Decision).order_by(Decision.title.asc()).all(),
        "all_risks": db.query(Risk).order_by(Risk.title.asc()).all(),
        "all_tasks": db.query(Task).order_by(Task.title.asc()).all(),
    }


@router.get("/requirements")
def list_requirements(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "requirements/list.html",
        {
            "requirements": _all_requirements(db),
            "all_stakeholders": db.query(Stakeholder).order_by(Stakeholder.name.asc()).all(),
            "all_decisions": db.query(Decision).order_by(Decision.title.asc()).all(),
            "all_risks": db.query(Risk).order_by(Risk.title.asc()).all(),
        },
    )


@router.post("/requirements")
def create_requirement(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    business_need: str = Form(""),
    acceptance_criteria: str = Form(""),
    status: str = Form("draft"),
    db: Session = Depends(get_db),
):
    if status not in VALID_REQUIREMENT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    workspace, user = seed_default_workspace(db)
    requirement = Requirement(
        workspace_id=workspace.id,
        owner_id=user.id,
        title=title,
        description=description,
        business_need=business_need,
        acceptance_criteria=acceptance_criteria,
        status=status,
    )
    db.add(requirement)
    db.commit()

    return templates.TemplateResponse(
        request, "requirements/_list_only.html", {"requirements": _all_requirements(db)}
    )


@router.get("/requirements/{requirement_id}")
def requirement_detail(request: Request, requirement_id: int, db: Session = Depends(get_db)):
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    return templates.TemplateResponse(
        request, "requirements/detail.html", _requirement_page_context(db, requirement)
    )


@router.patch("/requirements/{requirement_id}")
def edit_requirement(
    request: Request,
    requirement_id: int,
    title: str = Form(...),
    description: str = Form(""),
    business_need: str = Form(""),
    acceptance_criteria: str = Form(""),
    status: str = Form("draft"),
    db: Session = Depends(get_db),
):
    if status not in VALID_REQUIREMENT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    requirement.title = title
    requirement.description = description
    requirement.business_need = business_need
    requirement.acceptance_criteria = acceptance_criteria
    requirement.status = status
    db.commit()

    return templates.TemplateResponse(
        request, "requirements/_page.html", _requirement_page_context(db, requirement)
    )


@router.delete("/requirements/{requirement_id}")
def delete_requirement(requirement_id: int, db: Session = Depends(get_db)):
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    db.query(RequirementStakeholder).filter(
        RequirementStakeholder.requirement_id == requirement_id
    ).delete()
    db.query(RequirementDecision).filter(
        RequirementDecision.requirement_id == requirement_id
    ).delete()
    db.query(RequirementRisk).filter(RequirementRisk.requirement_id == requirement_id).delete()
    db.query(RequirementTask).filter(RequirementTask.requirement_id == requirement_id).delete()
    db.delete(requirement)
    db.commit()

    # A separate injected `response: Response` parameter's headers are NOT
    # merged when the endpoint explicitly returns its own Response object
    # (verified empirically) — set the header directly on the returned
    # Response instead.
    return Response(status_code=200, headers={"HX-Redirect": "/requirements"})


@router.post("/requirements/{requirement_id}/stakeholders")
def link_stakeholder(
    request: Request, requirement_id: int, stakeholder_id: int = Form(...), db: Session = Depends(get_db)
):
    requirement = db.get(Requirement, requirement_id)
    stakeholder = db.get(Stakeholder, stakeholder_id)
    if requirement is None or stakeholder is None:
        raise HTTPException(status_code=404, detail="Requirement or stakeholder not found")

    if stakeholder not in requirement.stakeholders:
        requirement.stakeholders.append(stakeholder)
        db.commit()

    return templates.TemplateResponse(
        request, "requirements/_page.html", _requirement_page_context(db, requirement)
    )


@router.post("/requirements/{requirement_id}/decisions")
def link_decision(
    request: Request, requirement_id: int, decision_id: int = Form(...), db: Session = Depends(get_db)
):
    requirement = db.get(Requirement, requirement_id)
    decision = db.get(Decision, decision_id)
    if requirement is None or decision is None:
        raise HTTPException(status_code=404, detail="Requirement or decision not found")

    if decision not in requirement.decisions:
        requirement.decisions.append(decision)
        db.commit()

    return templates.TemplateResponse(
        request, "requirements/_page.html", _requirement_page_context(db, requirement)
    )


@router.post("/requirements/{requirement_id}/risks")
def link_risk(
    request: Request, requirement_id: int, risk_id: int = Form(...), db: Session = Depends(get_db)
):
    requirement = db.get(Requirement, requirement_id)
    risk = db.get(Risk, risk_id)
    if requirement is None or risk is None:
        raise HTTPException(status_code=404, detail="Requirement or risk not found")

    if risk not in requirement.risks:
        requirement.risks.append(risk)
        db.commit()

    return templates.TemplateResponse(
        request, "requirements/_page.html", _requirement_page_context(db, requirement)
    )


@router.post("/requirements/{requirement_id}/tasks")
def link_task(
    request: Request, requirement_id: int, task_id: int = Form(...), db: Session = Depends(get_db)
):
    requirement = db.get(Requirement, requirement_id)
    task = db.get(Task, task_id)
    if requirement is None or task is None:
        raise HTTPException(status_code=404, detail="Requirement or task not found")

    if task not in requirement.tasks:
        requirement.tasks.append(task)
        db.commit()

    return templates.TemplateResponse(
        request, "requirements/_page.html", _requirement_page_context(db, requirement)
    )


@router.delete("/requirements/{requirement_id}/stakeholders/{stakeholder_id}")
def unlink_stakeholder(
    request: Request, requirement_id: int, stakeholder_id: int, db: Session = Depends(get_db)
):
    requirement = db.get(Requirement, requirement_id)
    stakeholder = db.get(Stakeholder, stakeholder_id)
    if requirement is None or stakeholder is None:
        raise HTTPException(status_code=404, detail="Requirement or stakeholder not found")

    if stakeholder in requirement.stakeholders:
        requirement.stakeholders.remove(stakeholder)
        db.commit()

    return templates.TemplateResponse(
        request, "requirements/_page.html", _requirement_page_context(db, requirement)
    )


@router.delete("/requirements/{requirement_id}/decisions/{decision_id}")
def unlink_decision(
    request: Request, requirement_id: int, decision_id: int, db: Session = Depends(get_db)
):
    requirement = db.get(Requirement, requirement_id)
    decision = db.get(Decision, decision_id)
    if requirement is None or decision is None:
        raise HTTPException(status_code=404, detail="Requirement or decision not found")

    if decision in requirement.decisions:
        requirement.decisions.remove(decision)
        db.commit()

    return templates.TemplateResponse(
        request, "requirements/_page.html", _requirement_page_context(db, requirement)
    )


@router.delete("/requirements/{requirement_id}/risks/{risk_id}")
def unlink_risk(
    request: Request, requirement_id: int, risk_id: int, db: Session = Depends(get_db)
):
    requirement = db.get(Requirement, requirement_id)
    risk = db.get(Risk, risk_id)
    if requirement is None or risk is None:
        raise HTTPException(status_code=404, detail="Requirement or risk not found")

    if risk in requirement.risks:
        requirement.risks.remove(risk)
        db.commit()

    return templates.TemplateResponse(
        request, "requirements/_page.html", _requirement_page_context(db, requirement)
    )


@router.delete("/requirements/{requirement_id}/tasks/{task_id}")
def unlink_task(
    request: Request, requirement_id: int, task_id: int, db: Session = Depends(get_db)
):
    requirement = db.get(Requirement, requirement_id)
    task = db.get(Task, task_id)
    if requirement is None or task is None:
        raise HTTPException(status_code=404, detail="Requirement or task not found")

    if task in requirement.tasks:
        requirement.tasks.remove(task)
        db.commit()

    return templates.TemplateResponse(
        request, "requirements/_page.html", _requirement_page_context(db, requirement)
    )
