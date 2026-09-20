from datetime import date as date_type

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Decision, RequirementDecision
from app.seed import seed_default_workspace

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _all_decisions(db: Session) -> list[Decision]:
    return db.query(Decision).order_by(Decision.title.asc()).all()


@router.post("/decisions")
def create_decision(
    request: Request,
    title: str = Form(...),
    rationale: str = Form(""),
    decided_at: str = Form(...),
    decided_by: str = Form(...),
    db: Session = Depends(get_db),
):
    workspace, _ = seed_default_workspace(db)
    decision = Decision(
        workspace_id=workspace.id,
        title=title,
        rationale=rationale,
        decided_at=date_type.fromisoformat(decided_at),
        decided_by=decided_by,
    )
    db.add(decision)
    db.commit()

    return templates.TemplateResponse(
        request, "decisions/_manager.html", {"all_decisions": _all_decisions(db)}
    )


@router.patch("/decisions/{decision_id}")
def edit_decision(
    request: Request,
    decision_id: int,
    title: str = Form(...),
    rationale: str = Form(""),
    decided_at: str = Form(...),
    decided_by: str = Form(...),
    db: Session = Depends(get_db),
):
    decision = db.get(Decision, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    decision.title = title
    decision.rationale = rationale
    decision.decided_at = date_type.fromisoformat(decided_at)
    decision.decided_by = decided_by
    db.commit()

    return templates.TemplateResponse(
        request, "decisions/_manager.html", {"all_decisions": _all_decisions(db)}
    )


@router.delete("/decisions/{decision_id}")
def delete_decision(request: Request, decision_id: int, db: Session = Depends(get_db)):
    decision = db.get(Decision, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    db.query(RequirementDecision).filter(RequirementDecision.decision_id == decision_id).delete()
    db.delete(decision)
    db.commit()

    return templates.TemplateResponse(
        request, "decisions/_manager.html", {"all_decisions": _all_decisions(db)}
    )
