from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Requirement

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/matrix")
def traceability_matrix(request: Request, db: Session = Depends(get_db)):
    requirements = db.query(Requirement).order_by(Requirement.title.asc()).all()
    return templates.TemplateResponse(
        request, "matrix/index.html", {"requirements": requirements}
    )
