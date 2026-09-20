from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Requirement
from app.services.traceability import traceability_status

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _link_badge_tier(count: int) -> str:
    if count == 0:
        return "missing"
    if count == 1:
        return "partial"
    return "linked"


def _needs_attention(requirements: list[Requirement]) -> list[dict]:
    at_risk = []
    draft = []
    for requirement in requirements:
        status = traceability_status(requirement)
        if status == "at_risk":
            open_high_risk = next(
                (r for r in requirement.risks if r.severity == "high" and r.status == "open"),
                None,
            )
            reason = (
                f"Risk: {open_high_risk.title[:40]}" if open_high_risk else "At risk"
            )
            at_risk.append({"requirement": requirement, "reason": reason, "status": "at_risk"})
        elif status == "draft":
            draft.append({"requirement": requirement, "reason": "No links yet", "status": "draft"})

    at_risk.sort(key=lambda item: item["requirement"].updated_at, reverse=True)
    draft.sort(key=lambda item: item["requirement"].updated_at, reverse=True)
    return (at_risk + draft)[:5]


@router.get("/matrix")
def traceability_matrix(request: Request, db: Session = Depends(get_db)):
    requirements = db.query(Requirement).order_by(Requirement.title.asc()).all()

    total = len(requirements)
    connected = sum(
        1
        for r in requirements
        if r.stakeholders or r.decisions or r.risks or r.tasks
    )
    orphaned = total - connected
    coverage_pct = round(connected / total * 100) if total > 0 else 0
    verified_count = sum(1 for r in requirements if traceability_status(r) == "verified")

    rows = []
    for requirement in requirements:
        rows.append(
            {
                "requirement": requirement,
                "status": traceability_status(requirement),
                "stakeholder_tier": _link_badge_tier(len(requirement.stakeholders)),
                "decision_tier": _link_badge_tier(len(requirement.decisions)),
                "risk_tier": _link_badge_tier(len(requirement.risks)),
                "task_tier": _link_badge_tier(len(requirement.tasks)),
            }
        )

    return templates.TemplateResponse(
        request,
        "matrix/index.html",
        {
            "rows": rows,
            "total_count": total,
            "connected_count": connected,
            "orphaned_count": orphaned,
            "coverage_pct": coverage_pct,
            "verified_count": verified_count,
            "needs_attention": _needs_attention(requirements),
            "active_nav": "matrix",
        },
    )
