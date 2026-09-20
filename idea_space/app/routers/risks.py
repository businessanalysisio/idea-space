from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import RequirementRisk, Risk
from app.seed import seed_default_workspace

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

VALID_SEVERITY_LIKELIHOOD = {"low", "medium", "high"}
VALID_RISK_STATUSES = {"open", "mitigated", "closed"}


def _all_risks(db: Session) -> list[Risk]:
    return db.query(Risk).order_by(Risk.title.asc()).all()


def _validate_risk_fields(severity: str, likelihood: str, status: str) -> None:
    if severity not in VALID_SEVERITY_LIKELIHOOD:
        raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")
    if likelihood not in VALID_SEVERITY_LIKELIHOOD:
        raise HTTPException(status_code=400, detail=f"Invalid likelihood: {likelihood}")
    if status not in VALID_RISK_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")


@router.post("/risks")
def create_risk(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    severity: str = Form("medium"),
    likelihood: str = Form("medium"),
    mitigation: str | None = Form(None),
    status: str = Form("open"),
    db: Session = Depends(get_db),
):
    _validate_risk_fields(severity, likelihood, status)

    workspace, _ = seed_default_workspace(db)
    risk = Risk(
        workspace_id=workspace.id,
        title=title,
        description=description,
        severity=severity,
        likelihood=likelihood,
        mitigation=mitigation or None,
        status=status,
    )
    db.add(risk)
    db.commit()

    return templates.TemplateResponse(
        request, "risks/_manager.html", {"all_risks": _all_risks(db)}
    )


@router.patch("/risks/{risk_id}")
def edit_risk(
    request: Request,
    risk_id: int,
    title: str = Form(...),
    description: str = Form(""),
    severity: str = Form("medium"),
    likelihood: str = Form("medium"),
    mitigation: str | None = Form(None),
    status: str = Form("open"),
    db: Session = Depends(get_db),
):
    _validate_risk_fields(severity, likelihood, status)

    risk = db.get(Risk, risk_id)
    if risk is None:
        raise HTTPException(status_code=404, detail="Risk not found")

    risk.title = title
    risk.description = description
    risk.severity = severity
    risk.likelihood = likelihood
    risk.mitigation = mitigation or None
    risk.status = status
    db.commit()

    return templates.TemplateResponse(
        request, "risks/_manager.html", {"all_risks": _all_risks(db)}
    )


@router.delete("/risks/{risk_id}")
def delete_risk(request: Request, risk_id: int, db: Session = Depends(get_db)):
    risk = db.get(Risk, risk_id)
    if risk is None:
        raise HTTPException(status_code=404, detail="Risk not found")

    db.query(RequirementRisk).filter(RequirementRisk.risk_id == risk_id).delete()
    db.delete(risk)
    db.commit()

    return templates.TemplateResponse(
        request, "risks/_manager.html", {"all_risks": _all_risks(db)}
    )
