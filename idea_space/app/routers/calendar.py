from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Task
from app.services.recurrence import project_occurrences

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

VALID_VIEWS = {"month", "week", "agenda"}


def _week_start(start_param: str | None) -> datetime:
    if start_param:
        day = datetime.strptime(start_param, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        today = datetime.now(timezone.utc)
        day = today - timedelta(days=today.weekday())
    return day.replace(hour=0, minute=0, second=0, microsecond=0)


def _month_start(month_param: str | None) -> date:
    if month_param:
        return datetime.strptime(month_param, "%Y-%m").date().replace(day=1)
    today = datetime.now(timezone.utc).date()
    return today.replace(day=1)


def _open_tasks_normalized(db: Session) -> list[Task]:
    open_tasks = db.query(Task).filter(Task.status == "open").all()
    for t in open_tasks:
        if t.due_date.tzinfo is None:
            t.due_date = t.due_date.replace(tzinfo=timezone.utc)
    return open_tasks


def _items_for_range(open_tasks: list[Task], range_start: datetime, range_end: datetime) -> list[dict]:
    real_items = [
        {"title": t.title, "due_date": t.due_date, "virtual": False, "id": t.id}
        for t in open_tasks
        if range_start <= t.due_date < range_end
    ]
    virtual_items = []
    for t in open_tasks:
        if not t.recurrence_active or t.due_date >= range_end:
            continue
        occurrences = project_occurrences(
            t.recurrence_pattern,
            t.recurrence_interval,
            t.recurrence_days_of_week,
            t.due_date,
            range_start,
            range_end,
        )
        for occ in occurrences:
            virtual_items.append({"title": t.title, "due_date": occ, "virtual": True})
    return sorted(real_items + virtual_items, key=lambda item: item["due_date"])


def _build_week_context(db: Session, start: str | None) -> dict:
    week_start = _week_start(start)
    week_end = week_start + timedelta(days=7)
    now = datetime.now(timezone.utc)
    open_tasks = _open_tasks_normalized(db)

    overdue = [t for t in open_tasks if t.due_date < week_start and t.due_date < now]

    days = []
    for offset in range(7):
        day_start = week_start + timedelta(days=offset)
        day_end = day_start + timedelta(days=1)
        days.append({"date": day_start, "items": _items_for_range(open_tasks, day_start, day_end)})

    return {"days": days, "overdue": overdue, "week_start": week_start, "week_start_str": week_start.strftime("%Y-%m-%d")}


def _build_month_context(db: Session, month: str | None) -> dict:
    month_start = _month_start(month)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    grid_start = month_start - timedelta(days=month_start.weekday())

    # Smallest multiple of 7, starting at 35 (5 rows), whose grid reaches
    # next_month — 5 rows covers most months, 6 rows (42) covers the rest.
    days_in_grid = 35
    while grid_start + timedelta(days=days_in_grid) < next_month:
        days_in_grid += 7

    open_tasks = _open_tasks_normalized(db)
    today = datetime.now(timezone.utc).date()

    weeks = []
    for week_offset in range(0, days_in_grid, 7):
        week_days = []
        for day_offset in range(7):
            day_date = grid_start + timedelta(days=week_offset + day_offset)
            day_start = datetime.combine(day_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            day_end = day_start + timedelta(days=1)
            week_days.append(
                {
                    "date": day_date,
                    "is_today": day_date == today,
                    "is_current_month": day_date.month == month_start.month,
                    "items": _items_for_range(open_tasks, day_start, day_end),
                }
            )
        weeks.append(week_days)

    return {
        "weeks": weeks,
        "month_start": month_start,
        "month_str": month_start.strftime("%Y-%m"),
        "month_label": month_start.strftime("%B %Y").upper(),
    }


def _build_agenda_context(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    range_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    range_end = range_start + timedelta(days=14)
    open_tasks = _open_tasks_normalized(db)
    items = _items_for_range(open_tasks, range_start, range_end)
    return {"items": items}


def _upcoming_day(db: Session) -> dict | None:
    now = datetime.now(timezone.utc)
    open_tasks = _open_tasks_normalized(db)
    for offset in range(14):
        day_start = (now + timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        items = _items_for_range(open_tasks, day_start, day_end)
        if items:
            return {"date": day_start, "items": items}
    return None


def _view_context_and_template(
    db: Session, view: str, month: str | None, start: str | None
) -> tuple[dict, str]:
    if view not in VALID_VIEWS:
        raise HTTPException(status_code=400, detail=f"Invalid view: {view}")

    if view == "month":
        return _build_month_context(db, month), "calendar/_month.html"
    if view == "week":
        return _build_week_context(db, start), "calendar/_week.html"
    return _build_agenda_context(db), "calendar/_agenda.html"


def render_calendar(
    request: Request,
    db: Session,
    view: str = "month",
    month: str | None = None,
    start: str | None = None,
):
    context, template_name = _view_context_and_template(db, view, month, start)
    context.update(
        {
            "view": view,
            "upcoming": _upcoming_day(db),
            "active_nav": "calendar",
        }
    )
    return templates.TemplateResponse(request, "calendar/index.html", {**context, "content_template": template_name})


def _render_calendar_fragment(
    request: Request,
    db: Session,
    view: str = "month",
    month: str | None = None,
    start: str | None = None,
):
    context, template_name = _view_context_and_template(db, view, month, start)
    context["view"] = view
    return templates.TemplateResponse(request, template_name, context)


@router.get("/calendar")
def calendar_page(
    request: Request,
    view: str = "month",
    month: str | None = None,
    start: str | None = None,
    db: Session = Depends(get_db),
):
    return render_calendar(request, db, view=view, month=month, start=start)
