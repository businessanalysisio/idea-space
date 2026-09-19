# Idea Space — Personal Workflow & Commitment Engine (Slice 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first vertical slice of Idea Space — a local FastAPI + SQLite + Jinja2/htmx web app delivering recurring tasks, calendar planning, labels/filtering, and reminders.

**Architecture:** Server-rendered Jinja2 templates + htmx for partial updates, no SPA framework. Recurrence is stored inline on the `task` row (generate-on-complete: completing a recurring task inserts its successor row rather than materializing future rows ahead of time). The calendar additionally computes non-persisted "virtual" future occurrences on the fly for preview.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (SQLite), Jinja2, htmx, python-dateutil, pytest, httpx (for `TestClient`).

**Spec:** `docs/superpowers/specs/2026-09-19-personal-workflow-engine-design.md`

## Global Constraints

- Single default `workspace` and `user` row seeded on startup — every `task`/`label` row carries `workspace_id`, every `task` carries `owner_id` (per spec's "future-proofing" section).
- All timestamps stored in UTC; conversion to local time happens only at display/template time.
- Recurrence fields live inline on `task` (no separate template table); completing a recurring task inserts a new `task` row with the same `recurrence_series_id`. Completed rows are never mutated again.
- Task `status` is one of `open` / `done` only (no `archived` status in this slice — out of scope per spec).
- Label filtering is OR-matching across selected labels; filter state lives in the URL query string.
- No e2e/browser test tooling in this slice — drag-and-drop and polling UI get manual verification, per spec.

---

## File Structure

```
idea_space/
  requirements.txt
  app/
    __init__.py
    main.py
    db.py
    models.py
    seed.py
    services/
      __init__.py
      recurrence.py
    routers/
      __init__.py
      tasks.py
      calendar.py
      labels.py
      reminders.py
    templates/
      base.html
      tasks/
        list.html
        _row.html
        _form.html
      calendar/
        week.html
      labels/
        _filter_bar.html
      reminders/
        _banner.html
    static/
      app.js
  tests/
    conftest.py
    test_models.py
    test_recurrence.py
    test_tasks.py
    test_calendar.py
    test_labels.py
    test_reminders.py
```

---

### Task 1: Project scaffolding, DB session, health check

**Files:**
- Create: `idea_space/requirements.txt`
- Create: `idea_space/app/__init__.py`
- Create: `idea_space/app/db.py`
- Create: `idea_space/app/main.py`
- Test: `idea_space/tests/conftest.py`
- Test: `idea_space/tests/test_health.py`

**Interfaces:**
- Produces: `app.db.Base` (SQLAlchemy `DeclarativeBase`), `app.db.engine`, `app.db.SessionLocal`, `app.db.get_db()` (FastAPI dependency, yields a `Session`). `app.main.app` (the `FastAPI` instance).

- [ ] **Step 1: Write requirements.txt**

```
fastapi==0.115.0
uvicorn==0.30.6
sqlalchemy==2.0.54
jinja2==3.1.4
python-multipart==0.0.9
python-dateutil==2.9.0.post0
pytest==8.3.3
httpx==0.27.2
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -r idea_space/requirements.txt`
Expected: all packages install without error.

- [ ] **Step 3: Write the failing test**

`idea_space/tests/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

`idea_space/tests/test_health.py`:

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'` (or `app` doesn't exist yet).

- [ ] **Step 5: Write db.py**

```python
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DB_PATH = os.environ.get("IDEA_SPACE_DB", "idea_space.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 6: Write app/__init__.py (empty) and main.py**

`idea_space/app/__init__.py`: empty file.

`idea_space/app/main.py`:

```python
from fastapi import FastAPI

app = FastAPI(title="Idea Space")


@app.get("/health")
def health_check():
    return {"status": "ok"}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd idea_space && python -m pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add idea_space/requirements.txt idea_space/app/__init__.py idea_space/app/db.py idea_space/app/main.py idea_space/tests/conftest.py idea_space/tests/test_health.py
git commit -m "feat: scaffold FastAPI app with DB session and health check"
```

---

### Task 2: Data models and default seed

**Files:**
- Create: `idea_space/app/models.py`
- Create: `idea_space/app/seed.py`
- Modify: `idea_space/app/main.py` (add startup event: create tables + seed)
- Modify: `idea_space/tests/conftest.py` (add `db_session` and `client` fixtures)
- Test: `idea_space/tests/test_models.py`

**Interfaces:**
- Consumes: `app.db.Base`, `app.db.engine`, `app.db.get_db` (Task 1).
- Produces: models `Workspace`, `User`, `Label`, `TaskLabel`, `Task`, `Reminder` (all `app.models.*`). `app.seed.seed_default_workspace(db: Session) -> tuple[Workspace, User]` — idempotent: returns the existing default workspace/user if already seeded, otherwise creates them.

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_models.py`:

```python
from datetime import datetime, timezone

from app.models import Task, Label, Reminder
from app.seed import seed_default_workspace


def test_seed_is_idempotent(db_session):
    workspace1, user1 = seed_default_workspace(db_session)
    workspace2, user2 = seed_default_workspace(db_session)

    assert workspace1.id == workspace2.id
    assert user1.id == user2.id
    assert workspace1.name == "My Workspace"


def test_task_defaults_to_open_status(db_session):
    workspace, user = seed_default_workspace(db_session)
    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Draft requirements outline",
        due_date=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add(task)
    db_session.commit()

    assert task.id is not None
    assert task.status == "open"
    assert task.recurrence_active is False
    assert task.recurrence_series_id is None


def test_task_label_many_to_many(db_session):
    workspace, user = seed_default_workspace(db_session)
    label = Label(workspace_id=workspace.id, name="Urgent", color="#ef4444")
    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Review stakeholder list",
        due_date=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
    )
    task.labels.append(label)
    db_session.add(task)
    db_session.commit()

    assert task.labels[0].name == "Urgent"


def test_reminder_links_to_task(db_session):
    workspace, user = seed_default_workspace(db_session)
    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Prep steering deck",
        due_date=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add(task)
    db_session.commit()

    reminder = Reminder(
        task_id=task.id,
        remind_at=datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc),
    )
    db_session.add(reminder)
    db_session.commit()

    assert reminder.id is not None
    assert reminder.dismissed_at is None
    assert reminder.snoozed_until is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models'` (and `db_session` fixture not found).

- [ ] **Step 3: Write app/models.py**

```python
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String(255))


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(20), default="#6b7280")


class TaskLabel(Base):
    __tablename__ = "task_labels"

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    label_id: Mapped[int] = mapped_column(ForeignKey("labels.id"), primary_key=True)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recurrence_series_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id"), nullable=True
    )
    recurrence_pattern: Mapped[str | None] = mapped_column(String(20), nullable=True)
    recurrence_interval: Mapped[int] = mapped_column(Integer, default=1)
    recurrence_days_of_week: Mapped[str | None] = mapped_column(String(20), nullable=True)
    recurrence_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    labels: Mapped[list[Label]] = relationship(secondary="task_labels")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Write app/seed.py**

```python
from sqlalchemy.orm import Session

from app.models import User, Workspace

DEFAULT_WORKSPACE_NAME = "My Workspace"
DEFAULT_USER_NAME = "Me"


def seed_default_workspace(db: Session) -> tuple[Workspace, User]:
    workspace = db.query(Workspace).filter_by(name=DEFAULT_WORKSPACE_NAME).first()
    if workspace is None:
        workspace = Workspace(name=DEFAULT_WORKSPACE_NAME)
        db.add(workspace)
        db.commit()
        db.refresh(workspace)

    user = db.query(User).filter_by(workspace_id=workspace.id).first()
    if user is None:
        user = User(workspace_id=workspace.id, name=DEFAULT_USER_NAME)
        db.add(user)
        db.commit()
        db.refresh(user)

    return workspace, user
```

- [ ] **Step 5: Update conftest.py with db_session and client fixtures**

`idea_space/tests/conftest.py` (replace full contents):

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

- [ ] **Step 6: Wire table creation and seeding into main.py startup**

Modify `idea_space/app/main.py`:

```python
from fastapi import FastAPI

from app.db import Base, SessionLocal, engine
from app.seed import seed_default_workspace

app = FastAPI(title="Idea Space")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_default_workspace(db)
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (5 tests total: 1 health + 4 model tests).

- [ ] **Step 8: Commit**

```bash
git add idea_space/app/models.py idea_space/app/seed.py idea_space/app/main.py idea_space/tests/conftest.py idea_space/tests/test_models.py
git commit -m "feat: add data models, default workspace/user seed, and test fixtures"
```

---

### Task 3: Recurrence calculation service

**Files:**
- Create: `idea_space/app/services/__init__.py`
- Create: `idea_space/app/services/recurrence.py`
- Test: `idea_space/tests/test_recurrence.py`

**Interfaces:**
- Produces: `app.services.recurrence.compute_next_due_date(pattern: str, interval: int, days_of_week: str | None, current_due_date: datetime) -> datetime | None`. `app.services.recurrence.project_occurrences(pattern: str, interval: int, days_of_week: str | None, from_due_date: datetime, range_start: datetime, range_end: datetime) -> list[datetime]` (virtual, non-persisted future occurrences within `[range_start, range_end]`, used by the calendar view in Task 7).

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_recurrence.py`:

```python
from datetime import datetime, timezone

from app.services.recurrence import compute_next_due_date, project_occurrences

UTC = timezone.utc


def test_daily_recurrence_adds_interval_days():
    current = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    result = compute_next_due_date("daily", 1, None, current)
    assert result == datetime(2026, 9, 21, 9, 0, tzinfo=UTC)


def test_daily_recurrence_respects_interval():
    current = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    result = compute_next_due_date("daily", 3, None, current)
    assert result == datetime(2026, 9, 23, 9, 0, tzinfo=UTC)


def test_weekly_recurrence_without_days_adds_interval_weeks():
    current = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)  # Sunday
    result = compute_next_due_date("weekly", 1, None, current)
    assert result == datetime(2026, 9, 27, 9, 0, tzinfo=UTC)


def test_monthly_recurrence_adds_interval_months():
    current = datetime(2026, 1, 31, 9, 0, tzinfo=UTC)
    result = compute_next_due_date("monthly", 1, None, current)
    assert result == datetime(2026, 2, 28, 9, 0, tzinfo=UTC)


def test_custom_recurrence_finds_next_matching_weekday():
    # Sunday 2026-09-20, custom days = Mon(0), Wed(2), Fri(4)
    current = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    result = compute_next_due_date("custom", 1, "0,2,4", current)
    assert result == datetime(2026, 9, 21, 9, 0, tzinfo=UTC)  # next Monday


def test_custom_recurrence_without_days_returns_none():
    current = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    result = compute_next_due_date("custom", 1, None, current)
    assert result is None


def test_unknown_pattern_returns_none():
    current = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    result = compute_next_due_date("yearly", 1, None, current)
    assert result is None


def test_project_occurrences_within_range():
    from_due = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    range_start = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
    range_end = datetime(2026, 10, 11, 0, 0, tzinfo=UTC)

    occurrences = project_occurrences("weekly", 1, None, from_due, range_start, range_end)

    assert occurrences == [
        datetime(2026, 9, 27, 9, 0, tzinfo=UTC),
        datetime(2026, 10, 4, 9, 0, tzinfo=UTC),
    ]


def test_project_occurrences_returns_empty_for_non_recurring():
    from_due = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    range_start = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
    range_end = datetime(2026, 10, 11, 0, 0, tzinfo=UTC)

    occurrences = project_occurrences(None, 1, None, from_due, range_start, range_end)

    assert occurrences == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_recurrence.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services'`.

- [ ] **Step 3: Write app/services/__init__.py (empty) and recurrence.py**

`idea_space/app/services/__init__.py`: empty file.

`idea_space/app/services/recurrence.py`:

```python
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

MAX_LOOKAHEAD_DAYS = 366


def compute_next_due_date(
    pattern: str | None,
    interval: int,
    days_of_week: str | None,
    current_due_date: datetime,
) -> datetime | None:
    if pattern == "daily":
        return current_due_date + timedelta(days=interval)

    if pattern == "weekly":
        if not days_of_week:
            return current_due_date + timedelta(weeks=interval)
        return _next_matching_weekday(current_due_date, days_of_week, interval)

    if pattern == "monthly":
        return current_due_date + relativedelta(months=interval)

    if pattern == "custom":
        if not days_of_week:
            return None
        return _next_matching_weekday(current_due_date, days_of_week, interval)

    return None


def _next_matching_weekday(
    current_due_date: datetime, days_of_week: str, interval: int
) -> datetime | None:
    allowed = {int(d) for d in days_of_week.split(",")}
    for offset in range(1, 7 * interval + 1):
        candidate = current_due_date + timedelta(days=offset)
        if candidate.weekday() in allowed:
            return candidate
    return None


def project_occurrences(
    pattern: str | None,
    interval: int,
    days_of_week: str | None,
    from_due_date: datetime,
    range_start: datetime,
    range_end: datetime,
) -> list[datetime]:
    if pattern is None:
        return []

    occurrences: list[datetime] = []
    current = from_due_date
    steps = 0
    while steps < MAX_LOOKAHEAD_DAYS:
        steps += 1
        next_date = compute_next_due_date(pattern, interval, days_of_week, current)
        if next_date is None or next_date > range_end:
            break
        if next_date >= range_start:
            occurrences.append(next_date)
        current = next_date

    return occurrences
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd idea_space && python -m pytest tests/test_recurrence.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add idea_space/app/services/__init__.py idea_space/app/services/recurrence.py idea_space/tests/test_recurrence.py
git commit -m "feat: add recurrence next-date calculation and virtual occurrence projection"
```

---

### Task 4: Task creation and listing (API + templates)

**Files:**
- Create: `idea_space/app/routers/__init__.py`
- Create: `idea_space/app/routers/tasks.py`
- Create: `idea_space/app/templates/base.html`
- Create: `idea_space/app/templates/tasks/list.html`
- Create: `idea_space/app/templates/tasks/_row.html`
- Create: `idea_space/app/templates/tasks/_form.html`
- Modify: `idea_space/app/main.py` (mount templates, static files, include `tasks` router)
- Test: `idea_space/tests/test_tasks.py`

**Interfaces:**
- Consumes: `app.db.get_db`, `app.models.Task`, `app.seed.seed_default_workspace` (Tasks 1-2).
- Produces: `POST /tasks` (form fields: `title`, `due_date` as `YYYY-MM-DDTHH:MM`, optional `recurrence_pattern`, `recurrence_interval`, `recurrence_days_of_week`) → creates a `Task`, returns rendered `tasks/list.html` fragment. `GET /tasks` → full page listing open tasks ordered by `due_date`, with overdue tasks (open, `due_date` < now) visually marked via a `task.is_overdue` flag passed to the template.

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_tasks.py`:

```python
from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def test_get_tasks_returns_empty_list_page(client):
    response = client.get("/tasks")
    assert response.status_code == 200
    assert b"No tasks yet" in response.content


def test_create_task_returns_it_in_list(client):
    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    response = client.post(
        "/tasks",
        data={"title": "Draft requirements outline", "due_date": due},
    )
    assert response.status_code == 200
    assert b"Draft requirements outline" in response.content

    listing = client.get("/tasks")
    assert b"Draft requirements outline" in listing.content


def test_create_recurring_task_stores_recurrence_fields(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post(
        "/tasks",
        data={
            "title": "Weekly status update",
            "due_date": due,
            "recurrence_pattern": "weekly",
            "recurrence_interval": "1",
        },
    )

    task = db_session.query(Task).filter_by(title="Weekly status update").one()
    assert task.recurrence_pattern == "weekly"
    assert task.recurrence_active is True
    assert task.recurrence_series_id == task.id


def test_overdue_task_is_flagged(client):
    overdue_due = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Send follow-up email", "due_date": overdue_due})

    response = client.get("/tasks")
    assert b"task--overdue" in response.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_tasks.py -v`
Expected: FAIL with `404 Not Found` for `/tasks` (route doesn't exist).

- [ ] **Step 3: Write app/routers/__init__.py (empty) and tasks.py**

`idea_space/app/routers/__init__.py`: empty file.

`idea_space/app/routers/tasks.py`:

```python
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Task
from app.seed import seed_default_workspace

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _attach_overdue_flag(tasks: list[Task]) -> list[Task]:
    now = datetime.now(timezone.utc)
    for task in tasks:
        task.is_overdue = task.status == "open" and task.due_date < now
    return tasks


def _open_tasks(db: Session) -> list[Task]:
    tasks = (
        db.query(Task)
        .filter(Task.status == "open")
        .order_by(Task.due_date.asc())
        .all()
    )
    return _attach_overdue_flag(tasks)


@router.get("/tasks")
def list_tasks(request: Request, db: Session = Depends(get_db)):
    tasks = _open_tasks(db)
    return templates.TemplateResponse(
        request, "tasks/list.html", {"tasks": tasks}
    )


@router.post("/tasks")
def create_task(
    request: Request,
    title: str = Form(...),
    due_date: str = Form(...),
    recurrence_pattern: str | None = Form(None),
    recurrence_interval: int = Form(1),
    recurrence_days_of_week: str | None = Form(None),
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

    if recurrence_pattern:
        task.recurrence_series_id = task.id
        db.commit()

    tasks = _open_tasks(db)
    return templates.TemplateResponse(
        request, "tasks/list.html", {"tasks": tasks}
    )
```

- [ ] **Step 4: Write templates**

`idea_space/app/templates/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Idea Space</title>
  <script src="https://unpkg.com/htmx.org@2.0.2"></script>
  <link rel="stylesheet" href="/static/app.css">
</head>
<body>
  <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

`idea_space/app/templates/tasks/_form.html`:

```html
<form hx-post="/tasks" hx-target="#task-list" hx-swap="outerHTML">
  <input type="text" name="title" placeholder="Task title" required>
  <input type="datetime-local" name="due_date" required>
  <select name="recurrence_pattern">
    <option value="">Does not repeat</option>
    <option value="daily">Daily</option>
    <option value="weekly">Weekly</option>
    <option value="monthly">Monthly</option>
    <option value="custom">Custom</option>
  </select>
  <input type="number" name="recurrence_interval" value="1" min="1">
  <input type="text" name="recurrence_days_of_week" placeholder="e.g. 0,2,4 (Mon,Wed,Fri)">
  <button type="submit">Add task</button>
</form>
```

`idea_space/app/templates/tasks/_row.html`:

```html
<li class="task{% if task.is_overdue %} task--overdue{% endif %}" data-task-id="{{ task.id }}" draggable="true">
  <span class="task-title">{{ task.title }}</span>
  <span class="task-due">{{ task.due_date.strftime('%Y-%m-%d %H:%M') }}</span>
  {% if task.recurrence_active %}<span class="task-recurring" title="Repeats {{ task.recurrence_pattern }}">↻</span>{% endif %}
</li>
```

`idea_space/app/templates/tasks/list.html`:

```html
{% extends "base.html" %}
{% block content %}
{% include "tasks/_form.html" %}
<ul id="task-list">
  {% if not tasks %}
  <p>No tasks yet — add one above.</p>
  {% else %}
  {% for task in tasks %}
    {% include "tasks/_row.html" %}
  {% endfor %}
  {% endif %}
</ul>
{% endblock %}
```

- [ ] **Step 5: Create empty static/app.css and wire main.py**

`idea_space/app/static/app.js`: empty file (real content added in Task 8).

Modify `idea_space/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import Base, SessionLocal, engine
from app.routers import tasks
from app.seed import seed_default_workspace

app = FastAPI(title="Idea Space")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(tasks.router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_default_workspace(db)
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}
```

Create an empty `idea_space/app/static/app.css` so `StaticFiles` has a directory to serve (an empty directory is fine — no file is strictly required, but keep this placeholder-free by adding one real rule):

```css
.task--overdue { color: #b91c1c; font-weight: 600; }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add idea_space/app/routers/__init__.py idea_space/app/routers/tasks.py idea_space/app/templates idea_space/app/static idea_space/app/main.py idea_space/tests/test_tasks.py
git commit -m "feat: add task creation and listing with overdue flagging"
```

---

### Task 5: Complete task with recurrence spawn

**Files:**
- Modify: `idea_space/app/routers/tasks.py` (add `POST /tasks/{task_id}/complete`)
- Modify: `idea_space/app/templates/tasks/_row.html` (add complete button)
- Test: `idea_space/tests/test_tasks.py` (append tests)

**Interfaces:**
- Consumes: `app.services.recurrence.compute_next_due_date` (Task 3), `Task` model (Task 2).
- Produces: `POST /tasks/{task_id}/complete` → marks the task `done`, sets `completed_at`; if `recurrence_active`, inserts a successor `Task` row (same `recurrence_series_id`, `recurrence_pattern`, `recurrence_interval`, `recurrence_days_of_week`, `recurrence_active=True`, new `due_date`, `status="open"`). Returns the updated `tasks/list.html` fragment.

- [ ] **Step 1: Write the failing test**

Append to `idea_space/tests/test_tasks.py`:

```python
def test_complete_non_recurring_task_removes_it_from_open_list(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "One-off review", "due_date": due})
    task = db_session.query(Task).filter_by(title="One-off review").one()

    response = client.post(f"/tasks/{task.id}/complete")
    assert response.status_code == 200
    assert b"One-off review" not in response.content

    db_session.refresh(task)
    assert task.status == "done"
    assert task.completed_at is not None


def test_completing_recurring_task_spawns_successor(client, db_session):
    from app.models import Task

    due = datetime(2026, 9, 20, 9, 0, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M")
    client.post(
        "/tasks",
        data={
            "title": "Weekly status update",
            "due_date": due,
            "recurrence_pattern": "weekly",
            "recurrence_interval": "1",
        },
    )
    original = db_session.query(Task).filter_by(title="Weekly status update").one()

    client.post(f"/tasks/{original.id}/complete")

    successor = (
        db_session.query(Task)
        .filter(Task.recurrence_series_id == original.recurrence_series_id, Task.id != original.id)
        .one()
    )
    assert successor.status == "open"
    assert successor.due_date == datetime(2026, 9, 27, 9, 0, tzinfo=UTC)
    assert successor.recurrence_active is True


def test_completing_paused_recurring_task_does_not_spawn_successor(client, db_session):
    from app.models import Task

    due = datetime(2026, 9, 20, 9, 0, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M")
    client.post(
        "/tasks",
        data={
            "title": "Monthly report",
            "due_date": due,
            "recurrence_pattern": "monthly",
            "recurrence_interval": "1",
        },
    )
    task = db_session.query(Task).filter_by(title="Monthly report").one()
    task.recurrence_active = False
    db_session.commit()

    client.post(f"/tasks/{task.id}/complete")

    successors = (
        db_session.query(Task)
        .filter(Task.recurrence_series_id == task.recurrence_series_id, Task.id != task.id)
        .all()
    )
    assert successors == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_tasks.py -v`
Expected: FAIL with `404 Not Found` for `POST /tasks/{id}/complete`.

- [ ] **Step 3: Add the complete endpoint**

Append to `idea_space/app/routers/tasks.py` (add import at top: `from datetime import datetime, timezone` already present; add `from fastapi import HTTPException`; add `from app.services.recurrence import compute_next_due_date`):

```python
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from app.services.recurrence import compute_next_due_date
```

```python
@router.post("/tasks/{task_id}/complete")
def complete_task(request: Request, task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = "done"
    task.completed_at = datetime.now(timezone.utc)
    db.commit()

    if task.recurrence_active:
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
            )
            db.add(successor)
            db.commit()

    tasks = _open_tasks(db)
    return templates.TemplateResponse(
        request, "tasks/list.html", {"tasks": tasks}
    )
```

- [ ] **Step 4: Add complete button to the row template**

Modify `idea_space/app/templates/tasks/_row.html`:

```html
<li class="task{% if task.is_overdue %} task--overdue{% endif %}" data-task-id="{{ task.id }}" draggable="true">
  <span class="task-title">{{ task.title }}</span>
  <span class="task-due">{{ task.due_date.strftime('%Y-%m-%d %H:%M') }}</span>
  {% if task.recurrence_active %}<span class="task-recurring" title="Repeats {{ task.recurrence_pattern }}">↻</span>{% endif %}
  <button hx-post="/tasks/{{ task.id }}/complete" hx-target="#task-list" hx-swap="outerHTML">Done</button>
</li>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add idea_space/app/routers/tasks.py idea_space/app/templates/tasks/_row.html idea_space/tests/test_tasks.py
git commit -m "feat: complete tasks and auto-spawn the next recurring instance"
```

---

### Task 6: Pause/stop recurrence

**Files:**
- Modify: `idea_space/app/routers/tasks.py` (add `PATCH /tasks/{task_id}/recurrence`)
- Modify: `idea_space/app/templates/tasks/_row.html` (add pause/resume control)
- Test: `idea_space/tests/test_tasks.py` (append tests)

**Interfaces:**
- Consumes: `Task` model (Task 2).
- Produces: `PATCH /tasks/{task_id}/recurrence` (form field `active`: `"true"`/`"false"`) → sets `task.recurrence_active`. Returns the updated `tasks/list.html` fragment. 404 if the task has no recurrence pattern set.

- [ ] **Step 1: Write the failing test**

Append to `idea_space/tests/test_tasks.py`:

```python
def test_pause_recurrence_sets_inactive(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post(
        "/tasks",
        data={"title": "Daily standup", "due_date": due, "recurrence_pattern": "daily"},
    )
    task = db_session.query(Task).filter_by(title="Daily standup").one()

    response = client.patch(f"/tasks/{task.id}/recurrence", data={"active": "false"})
    assert response.status_code == 200

    db_session.refresh(task)
    assert task.recurrence_active is False


def test_pause_recurrence_on_non_recurring_task_returns_404(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "One-off review", "due_date": due})
    task = db_session.query(Task).filter_by(title="One-off review").one()

    response = client.patch(f"/tasks/{task.id}/recurrence", data={"active": "false"})
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_tasks.py -v`
Expected: FAIL — `PATCH /tasks/{id}/recurrence` not found (405/404).

- [ ] **Step 3: Add the endpoint**

Append to `idea_space/app/routers/tasks.py`:

```python
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
    return templates.TemplateResponse(
        request, "tasks/list.html", {"tasks": tasks}
    )
```

- [ ] **Step 4: Add pause/resume control to the row template**

Modify `idea_space/app/templates/tasks/_row.html`:

```html
<li class="task{% if task.is_overdue %} task--overdue{% endif %}" data-task-id="{{ task.id }}" draggable="true">
  <span class="task-title">{{ task.title }}</span>
  <span class="task-due">{{ task.due_date.strftime('%Y-%m-%d %H:%M') }}</span>
  {% if task.recurrence_pattern %}
    <span class="task-recurring" title="Repeats {{ task.recurrence_pattern }}">↻</span>
    <button
      hx-patch="/tasks/{{ task.id }}/recurrence"
      hx-vals='{"active": "{{ "false" if task.recurrence_active else "true" }}"}'
      hx-target="#task-list" hx-swap="outerHTML">
      {{ "Pause" if task.recurrence_active else "Resume" }}
    </button>
  {% endif %}
  <button hx-post="/tasks/{{ task.id }}/complete" hx-target="#task-list" hx-swap="outerHTML">Done</button>
</li>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add idea_space/app/routers/tasks.py idea_space/app/templates/tasks/_row.html idea_space/tests/test_tasks.py
git commit -m "feat: pause and resume task recurrence"
```

---

### Task 7: Calendar view with virtual occurrence projection

**Files:**
- Create: `idea_space/app/routers/calendar.py`
- Create: `idea_space/app/templates/calendar/week.html`
- Modify: `idea_space/app/main.py` (include `calendar` router)
- Test: `idea_space/tests/test_calendar.py`

**Interfaces:**
- Consumes: `app.services.recurrence.project_occurrences` (Task 3), `Task` model (Task 2).
- Produces: `GET /calendar?start=YYYY-MM-DD` → renders a 7-day week grid starting from `start` (defaults to the current week's Monday if omitted). Each day cell lists: real open `Task` rows due that day, plus virtual occurrences (dicts `{"title": str, "due_date": datetime, "virtual": True}`) projected from every recurring task whose current instance falls before that day. Overdue open tasks (due before the week's start, still `open`) are listed separately under an "Overdue" section at the top regardless of the viewed week.

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_calendar.py`:

```python
from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def test_calendar_week_shows_real_task_on_its_day(client):
    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)  # Tuesday
    client.post(
        "/tasks",
        data={"title": "Stakeholder sync", "due_date": due.strftime("%Y-%m-%dT%H:%M")},
    )

    response = client.get("/calendar?start=2026-09-21")
    assert response.status_code == 200
    assert b"Stakeholder sync" in response.content


def test_calendar_week_shows_virtual_projected_occurrence(client):
    due = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)  # Sunday, week 1
    client.post(
        "/tasks",
        data={
            "title": "Weekly status update",
            "due_date": due.strftime("%Y-%m-%dT%H:%M"),
            "recurrence_pattern": "weekly",
            "recurrence_interval": "1",
        },
    )

    # Week of 2026-09-27 has no real row yet, only the virtual projection.
    response = client.get("/calendar?start=2026-09-21")
    assert b"task--virtual" in response.content
    assert b"Weekly status update" in response.content


def test_calendar_week_lists_overdue_tasks_from_before_the_range(client):
    overdue_due = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    client.post(
        "/tasks",
        data={"title": "Send follow-up email", "due_date": overdue_due.strftime("%Y-%m-%dT%H:%M")},
    )

    response = client.get("/calendar?start=2026-09-21")
    assert b"Send follow-up email" in response.content
    assert b"calendar-overdue" in response.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_calendar.py -v`
Expected: FAIL with `404 Not Found` for `/calendar`.

- [ ] **Step 3: Write app/routers/calendar.py**

```python
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Task
from app.services.recurrence import project_occurrences

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _week_start(start_param: str | None) -> datetime:
    if start_param:
        day = datetime.strptime(start_param, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        today = datetime.now(timezone.utc)
        day = today - timedelta(days=today.weekday())
    return day.replace(hour=0, minute=0, second=0, microsecond=0)


@router.get("/calendar")
def calendar_week(request: Request, start: str | None = None, db: Session = Depends(get_db)):
    week_start = _week_start(start)
    week_end = week_start + timedelta(days=7)
    now = datetime.now(timezone.utc)

    open_tasks = db.query(Task).filter(Task.status == "open").all()

    overdue = [t for t in open_tasks if t.due_date < week_start and t.due_date < now]

    days = []
    for offset in range(7):
        day_start = week_start + timedelta(days=offset)
        day_end = day_start + timedelta(days=1)

        real_items = [
            {"title": t.title, "due_date": t.due_date, "virtual": False, "id": t.id}
            for t in open_tasks
            if day_start <= t.due_date < day_end
        ]

        virtual_items = []
        for t in open_tasks:
            if not t.recurrence_active or t.due_date >= day_end:
                continue
            occurrences = project_occurrences(
                t.recurrence_pattern,
                t.recurrence_interval,
                t.recurrence_days_of_week,
                t.due_date,
                day_start,
                day_end,
            )
            for occ in occurrences:
                virtual_items.append({"title": t.title, "due_date": occ, "virtual": True})

        days.append({"date": day_start, "items": real_items + virtual_items})

    return templates.TemplateResponse(
        request,
        "calendar/week.html",
        {"days": days, "overdue": overdue, "week_start": week_start},
    )
```

- [ ] **Step 4: Write templates/calendar/week.html**

```html
{% extends "base.html" %}
{% block content %}
{% if overdue %}
<section class="calendar-overdue">
  <h2>Overdue</h2>
  <ul>
    {% for task in overdue %}
    <li class="task task--overdue" data-task-id="{{ task.id }}">{{ task.title }} — {{ task.due_date.strftime('%Y-%m-%d') }}</li>
    {% endfor %}
  </ul>
</section>
{% endif %}
<div class="calendar-week">
  {% for day in days %}
  <div class="calendar-day" data-date="{{ day.date.strftime('%Y-%m-%d') }}">
    <h3>{{ day.date.strftime('%a %b %d') }}</h3>
    <ul>
      {% for item in day.items %}
      <li class="task{% if item.virtual %} task--virtual{% endif %}"
          {% if not item.virtual %}data-task-id="{{ item.id }}" draggable="true"{% endif %}>
        {{ item.title }}
      </li>
      {% endfor %}
    </ul>
  </div>
  {% endfor %}
</div>
{% endblock %}
```

- [ ] **Step 5: Wire the router into main.py**

Modify `idea_space/app/main.py`: add `from app.routers import calendar` and `app.include_router(calendar.router)` alongside the existing `tasks` router include.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add idea_space/app/routers/calendar.py idea_space/app/templates/calendar idea_space/app/main.py idea_space/tests/test_calendar.py
git commit -m "feat: add week calendar view with virtual recurrence projection and overdue section"
```

---

### Task 8: Drag-to-reschedule

**Files:**
- Modify: `idea_space/app/routers/tasks.py` (add `PATCH /tasks/{task_id}/reschedule`)
- Modify: `idea_space/app/static/app.js` (drag-and-drop wiring)
- Modify: `idea_space/app/templates/calendar/week.html` (drop targets + script include)
- Modify: `idea_space/app/templates/base.html` (include `app.js`)
- Test: `idea_space/tests/test_tasks.py` (append test)

**Interfaces:**
- Consumes: `Task` model (Task 2).
- Produces: `PATCH /tasks/{task_id}/reschedule` (form field `due_date`: `YYYY-MM-DD`, preserves existing time-of-day) → updates `task.due_date`, returns the updated `calendar/week.html` fragment for the task's current week. 404 for unknown/non-open task ids.

- [ ] **Step 1: Write the failing test**

Append to `idea_space/tests/test_tasks.py`:

```python
def test_reschedule_moves_task_to_new_date(client, db_session):
    from app.models import Task

    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    client.post(
        "/tasks",
        data={"title": "Stakeholder sync", "due_date": due.strftime("%Y-%m-%dT%H:%M")},
    )
    task = db_session.query(Task).filter_by(title="Stakeholder sync").one()

    response = client.patch(f"/tasks/{task.id}/reschedule", data={"due_date": "2026-09-24"})
    assert response.status_code == 200

    db_session.refresh(task)
    assert task.due_date.date().isoformat() == "2026-09-24"
    assert task.due_date.time().isoformat() == "10:00:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_tasks.py -v`
Expected: FAIL — `PATCH /tasks/{id}/reschedule` not found.

- [ ] **Step 3: Add the endpoint**

Append to `idea_space/app/routers/tasks.py`:

```python
from app.routers import calendar as calendar_router


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
```

**Note:** this reuses `calendar_week`'s own week (current week) rather than the week the drag happened in, since the task's own `_week_start` recomputes from "now" — acceptable for v1 (the htmx response re-renders whichever week is current; if the user was viewing a different week, a follow-up `GET /calendar?start=...` via the day-cell's own hx-get, wired in Step 4 below, keeps the visible week in sync).

- [ ] **Step 4: Add drop targets in the template and drag/drop JS**

Modify `idea_space/app/templates/calendar/week.html` — add `hx-*` drop wiring via `app.js` instead of inline handlers, and pass the currently viewed week start to JS:

```html
{% extends "base.html" %}
{% block content %}
<div class="calendar-week" data-week-start="{{ week_start.strftime('%Y-%m-%d') }}">
  {% if overdue %}
  <section class="calendar-overdue">
    <h2>Overdue</h2>
    <ul>
      {% for task in overdue %}
      <li class="task task--overdue" data-task-id="{{ task.id }}">{{ task.title }} — {{ task.due_date.strftime('%Y-%m-%d') }}</li>
      {% endfor %}
    </ul>
  </section>
  {% endif %}
  {% for day in days %}
  <div class="calendar-day" data-date="{{ day.date.strftime('%Y-%m-%d') }}">
    <h3>{{ day.date.strftime('%a %b %d') }}</h3>
    <ul>
      {% for item in day.items %}
      <li class="task{% if item.virtual %} task--virtual{% endif %}"
          {% if not item.virtual %}data-task-id="{{ item.id }}" draggable="true"{% endif %}>
        {{ item.title }}
      </li>
      {% endfor %}
    </ul>
  </div>
  {% endfor %}
</div>
{% endblock %}
```

Modify `idea_space/app/templates/base.html` to include the script before `</body>`:

```html
  <script src="/static/app.js"></script>
</body>
</html>
```

Replace `idea_space/app/static/app.js` (empty from Task 4) with:

```javascript
document.body.addEventListener("dragstart", (event) => {
  const taskEl = event.target.closest("li[data-task-id]");
  if (!taskEl) return;
  event.dataTransfer.setData("text/task-id", taskEl.dataset.taskId);
});

document.body.addEventListener("dragover", (event) => {
  if (event.target.closest(".calendar-day")) {
    event.preventDefault();
  }
});

document.body.addEventListener("drop", async (event) => {
  const dayEl = event.target.closest(".calendar-day");
  if (!dayEl) return;
  event.preventDefault();

  const taskId = event.dataTransfer.getData("text/task-id");
  if (!taskId) return;

  const newDate = dayEl.dataset.date;
  const response = await fetch(`/tasks/${taskId}/reschedule`, {
    method: "PATCH",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `due_date=${encodeURIComponent(newDate)}`,
  });

  if (response.ok) {
    const html = await response.text();
    document.querySelector("main").innerHTML = html;
  }
});
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS. (Drag-and-drop itself is verified manually per the spec's testing section — the endpoint tests cover the persisted behavior.)

- [ ] **Step 6: Manual verification**

Run: `cd idea_space && uvicorn app.main:app --reload`, open `http://127.0.0.1:8000/calendar` in a browser, create a task, drag it to another day cell, and confirm the card moves and the page reflects the new date (fewer than 3 actions: drag, drop — 2 actions, satisfying the spec's AC).

- [ ] **Step 7: Commit**

```bash
git add idea_space/app/routers/tasks.py idea_space/app/static/app.js idea_space/app/templates/calendar/week.html idea_space/app/templates/base.html idea_space/tests/test_tasks.py
git commit -m "feat: drag-and-drop task rescheduling on the calendar"
```

---

### Task 9: Labels CRUD and assignment

**Files:**
- Create: `idea_space/app/routers/labels.py`
- Modify: `idea_space/app/templates/tasks/_row.html` (show assigned labels)
- Modify: `idea_space/app/templates/tasks/_form.html` (label multi-select on create)
- Modify: `idea_space/app/main.py` (include `labels` router)
- Test: `idea_space/tests/test_labels.py`

**Interfaces:**
- Consumes: `Label`, `Task` models (Task 2).
- Produces: `POST /labels` (form: `name`, `color`) → creates a `Label`, returns a `labels/_filter_bar.html` fragment listing all labels. `PATCH /labels/{label_id}` (form: `name`) → renames. `DELETE /labels/{label_id}` → deletes the label and its `task_labels` join rows (tasks untouched). `POST /tasks/{task_id}/labels` (form: `label_id`) → appends a label to a task's `labels` list (idempotent — no duplicate).

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_labels.py`:

```python
from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def test_create_label(client):
    response = client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})
    assert response.status_code == 200
    assert b"Urgent" in response.content


def test_rename_label(client, db_session):
    from app.models import Label

    client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})
    label = db_session.query(Label).filter_by(name="Urgent").one()

    response = client.patch(f"/labels/{label.id}", data={"name": "High Priority"})
    assert response.status_code == 200
    assert b"High Priority" in response.content

    db_session.refresh(label)
    assert label.name == "High Priority"


def test_delete_label_removes_it_but_keeps_task(client, db_session):
    from app.models import Label, Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})

    task = db_session.query(Task).filter_by(title="Draft outline").one()
    label = db_session.query(Label).filter_by(name="Urgent").one()
    client.post(f"/tasks/{task.id}/labels", data={"label_id": label.id})

    response = client.delete(f"/labels/{label.id}")
    assert response.status_code == 200

    db_session.expire_all()
    assert db_session.query(Label).filter_by(id=label.id).first() is None
    remaining_task = db_session.query(Task).filter_by(id=task.id).one()
    assert remaining_task.labels == []


def test_assign_label_to_task(client, db_session):
    from app.models import Label, Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})

    task = db_session.query(Task).filter_by(title="Draft outline").one()
    label = db_session.query(Label).filter_by(name="Urgent").one()

    response = client.post(f"/tasks/{task.id}/labels", data={"label_id": label.id})
    assert response.status_code == 200
    assert b"Urgent" in response.content

    db_session.refresh(task)
    assert [l.name for l in task.labels] == ["Urgent"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_labels.py -v`
Expected: FAIL with `404 Not Found` for `/labels`.

- [ ] **Step 3: Write app/routers/labels.py**

```python
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Label, Task
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
        request, "labels/_filter_bar.html", {"labels": _all_labels(db)}
    )


@router.patch("/labels/{label_id}")
def rename_label(request: Request, label_id: int, name: str = Form(...), db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found")

    label.name = name
    db.commit()

    return templates.TemplateResponse(
        request, "labels/_filter_bar.html", {"labels": _all_labels(db)}
    )


@router.delete("/labels/{label_id}")
def delete_label(request: Request, label_id: int, db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found")

    db.delete(label)
    db.commit()

    return templates.TemplateResponse(
        request, "labels/_filter_bar.html", {"labels": _all_labels(db)}
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
    return templates.TemplateResponse(request, "tasks/list.html", {"tasks": tasks})
```

- [ ] **Step 4: Write templates/labels/_filter_bar.html**

```html
<div id="label-filter-bar">
  {% for label in labels %}
  <span class="label-chip" style="background-color: {{ label.color }};">{{ label.name }}</span>
  {% endfor %}
</div>
```

- [ ] **Step 5: Show assigned labels on task rows**

Modify `idea_space/app/templates/tasks/_row.html` — add after the recurrence span:

```html
  {% for label in task.labels %}
  <span class="label-chip" style="background-color: {{ label.color }};">{{ label.name }}</span>
  {% endfor %}
```

- [ ] **Step 6: Wire the router into main.py**

Modify `idea_space/app/main.py`: add `from app.routers import labels` and `app.include_router(labels.router)`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add idea_space/app/routers/labels.py idea_space/app/templates/labels idea_space/app/templates/tasks/_row.html idea_space/app/main.py idea_space/tests/test_labels.py
git commit -m "feat: add label CRUD and task-label assignment"
```

---

### Task 10: Label and status filtering on the task list

**Files:**
- Modify: `idea_space/app/routers/tasks.py` (extend `GET /tasks` with `labels` and `status` query params)
- Modify: `idea_space/app/templates/tasks/list.html` (filter bar + clear-filters control)
- Test: `idea_space/tests/test_tasks.py` (append tests)

**Interfaces:**
- Consumes: `Label`, `Task`, `TaskLabel` models (Task 2), `labels/_filter_bar.html` (Task 9).
- Produces: `GET /tasks?labels=1,2&status=open` → OR-matches tasks against any of the given label ids; `status` filters `open`/`done`/omitted-means-`open`. Filter state round-trips via the URL query string; a "Clear filters" link resets to `/tasks`.

- [ ] **Step 1: Write the failing test**

Append to `idea_space/tests/test_tasks.py`:

```python
def test_filter_tasks_by_label(client, db_session):
    from app.models import Label, Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    client.post("/tasks", data={"title": "Review budget", "due_date": due})
    client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})

    outline = db_session.query(Task).filter_by(title="Draft outline").one()
    label = db_session.query(Label).filter_by(name="Urgent").one()
    client.post(f"/tasks/{outline.id}/labels", data={"label_id": label.id})

    response = client.get(f"/tasks?labels={label.id}")
    assert b"Draft outline" in response.content
    assert b"Review budget" not in response.content


def test_filter_tasks_by_multiple_labels_is_or_matched(client, db_session):
    from app.models import Label, Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    client.post("/tasks", data={"title": "Review budget", "due_date": due})
    client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})
    client.post("/labels", data={"name": "Finance", "color": "#3b82f6"})

    outline = db_session.query(Task).filter_by(title="Draft outline").one()
    budget = db_session.query(Task).filter_by(title="Review budget").one()
    urgent = db_session.query(Label).filter_by(name="Urgent").one()
    finance = db_session.query(Label).filter_by(name="Finance").one()
    client.post(f"/tasks/{outline.id}/labels", data={"label_id": urgent.id})
    client.post(f"/tasks/{budget.id}/labels", data={"label_id": finance.id})

    response = client.get(f"/tasks?labels={urgent.id},{finance.id}")
    assert b"Draft outline" in response.content
    assert b"Review budget" in response.content


def test_clear_filters_link_present(client):
    response = client.get("/tasks?labels=1&status=open")
    assert b'href="/tasks"' in response.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_tasks.py -v`
Expected: FAIL — label filter has no effect yet (both tasks returned), and no clear-filters link.

- [ ] **Step 3: Extend list_tasks with filtering**

Modify `idea_space/app/routers/tasks.py` — replace `_open_tasks` and `list_tasks` with:

```python
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
```

Add `from app.models import Label` to the existing `from app.models import Task` import line (making it `from app.models import Label, Task`).

- [ ] **Step 4: Add filter bar and clear-filters link to list.html**

Modify `idea_space/app/templates/tasks/list.html`:

```html
{% extends "base.html" %}
{% block content %}
{% include "tasks/_form.html" %}
<nav class="filter-bar">
  {% for label in all_labels|default([]) %}
  <a href="/tasks?labels={{ label.id }}{% if status|default('open') != 'open' %}&status={{ status }}{% endif %}"
     class="label-chip{% if label.id in selected_label_ids|default([]) %} label-chip--active{% endif %}"
     style="background-color: {{ label.color }};">{{ label.name }}</a>
  {% endfor %}
  <a href="/tasks">Clear filters</a>
</nav>
<ul id="task-list">
  {% if not tasks %}
  <p>No tasks yet — add one above.</p>
  {% else %}
  {% for task in tasks %}
    {% include "tasks/_row.html" %}
  {% endfor %}
  {% endif %}
</ul>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS.

**Note:** `list_tasks` is also invoked directly (not via HTTP) as the response for `POST /tasks`, `POST /tasks/{id}/complete`, and `PATCH /tasks/{id}/recurrence`, which currently call `_open_tasks(db)` and pass only `{"tasks": tasks}` to the template. Since `list.html` now references `all_labels`, `selected_label_ids`, and `status`, update those three response blocks (in `create_task`, `complete_task`, `set_recurrence_active`) to build their context the same way `list_tasks` does:

```python
    tasks = _open_tasks(db)
    all_labels = db.query(Label).order_by(Label.name.asc()).all()
    return templates.TemplateResponse(
        request,
        "tasks/list.html",
        {"tasks": tasks, "all_labels": all_labels, "selected_label_ids": [], "status": "open"},
    )
```

Re-run: `cd idea_space && python -m pytest tests/ -v` — Expected: all PASS (this fixes `create_task`/`complete_task`/`set_recurrence_active` responses that would otherwise raise a Jinja2 `UndefinedError` on `all_labels`).

**Preflight ruling (recorded in the SDD ledger):** Task 9's `assign_label` endpoint (in `routers/labels.py`) also renders `tasks/list.html` and was not in the three-call-site list above. Rather than adding a fourth call site to patch, the `list.html` snippet in Step 4 uses `|default([])` on `all_labels` and `selected_label_ids` and `|default('open')` on `status`, so any caller that omits them (including `assign_label`) renders an empty/neutral filter bar instead of raising `UndefinedError`. The three explicit call-site fixes above remain required for correct behavior (a populated, accurate filter bar) on those endpoints; `assign_label`'s filter bar will render empty until the next full `GET /tasks` — acceptable for this slice, not a crash.

- [ ] **Step 6: Commit**

```bash
git add idea_space/app/routers/tasks.py idea_space/app/templates/tasks/list.html idea_space/tests/test_tasks.py
git commit -m "feat: filter tasks by label and status with a clear-filters control"
```

---

### Task 11: Reminders — CRUD, due query, snooze/dismiss, polling banner

**Files:**
- Create: `idea_space/app/routers/reminders.py`
- Create: `idea_space/app/templates/reminders/_banner.html`
- Modify: `idea_space/app/templates/tasks/_form.html` (optional `remind_at` field)
- Modify: `idea_space/app/routers/tasks.py` (accept `remind_at` on task creation, create a `Reminder`)
- Modify: `idea_space/app/templates/base.html` (mount the polling banner via htmx)
- Modify: `idea_space/app/main.py` (include `reminders` router)
- Test: `idea_space/tests/test_reminders.py`

**Interfaces:**
- Consumes: `Reminder`, `Task` models (Task 2).
- Produces: `GET /reminders/due` → renders `reminders/_banner.html` with reminders where `remind_at <= now`, `dismissed_at IS NULL`, `(snoozed_until IS NULL OR snoozed_until <= now)`, and the linked task's `status == "open"`. `POST /reminders/{reminder_id}/dismiss` → sets `dismissed_at`. `POST /reminders/{reminder_id}/snooze` (form `minutes`, default 15) → sets `snoozed_until = now + minutes`. Both return the refreshed banner fragment.

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_reminders.py`:

```python
from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def _create_task_with_reminder(client, db_session, title, remind_offset_minutes):
    from app.models import Task, Reminder

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": title, "due_date": due})
    task = db_session.query(Task).filter_by(title=title).one()

    reminder = Reminder(
        task_id=task.id,
        remind_at=datetime.now(UTC) + timedelta(minutes=remind_offset_minutes),
    )
    db_session.add(reminder)
    db_session.commit()
    db_session.refresh(reminder)
    return task, reminder


def test_due_reminders_shows_past_due_reminder(client, db_session):
    _create_task_with_reminder(client, db_session, "Prep steering deck", -5)

    response = client.get("/reminders/due")
    assert response.status_code == 200
    assert b"Prep steering deck" in response.content


def test_due_reminders_excludes_future_reminder(client, db_session):
    _create_task_with_reminder(client, db_session, "Prep steering deck", 60)

    response = client.get("/reminders/due")
    assert b"Prep steering deck" not in response.content


def test_dismiss_reminder_removes_it_from_due_list(client, db_session):
    _, reminder = _create_task_with_reminder(client, db_session, "Prep steering deck", -5)

    response = client.post(f"/reminders/{reminder.id}/dismiss")
    assert response.status_code == 200
    assert b"Prep steering deck" not in response.content

    db_session.refresh(reminder)
    assert reminder.dismissed_at is not None


def test_snooze_reminder_hides_it_until_snooze_expires(client, db_session):
    _, reminder = _create_task_with_reminder(client, db_session, "Prep steering deck", -5)

    response = client.post(f"/reminders/{reminder.id}/snooze", data={"minutes": "15"})
    assert response.status_code == 200
    assert b"Prep steering deck" not in response.content

    db_session.refresh(reminder)
    assert reminder.snoozed_until > datetime.now(UTC)


def test_completed_task_suppresses_its_reminder(client, db_session):
    task, _ = _create_task_with_reminder(client, db_session, "Prep steering deck", -5)

    client.post(f"/tasks/{task.id}/complete")

    response = client.get("/reminders/due")
    assert b"Prep steering deck" not in response.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_reminders.py -v`
Expected: FAIL with `404 Not Found` for `/reminders/due`.

- [ ] **Step 3: Write app/routers/reminders.py**

```python
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Reminder, Task

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _due_reminders(db: Session) -> list[Reminder]:
    now = datetime.now(timezone.utc)
    reminders = (
        db.query(Reminder)
        .join(Task, Reminder.task_id == Task.id)
        .filter(
            Reminder.remind_at <= now,
            Reminder.dismissed_at.is_(None),
            Task.status == "open",
        )
        .all()
    )
    due = [r for r in reminders if r.snoozed_until is None or r.snoozed_until <= now]
    for r in due:
        r.task_title = r.task.title
    return due


@router.get("/reminders/due")
def due_reminders(request: Request, db: Session = Depends(get_db)):
    reminders = _due_reminders(db)
    return templates.TemplateResponse(
        request, "reminders/_banner.html", {"reminders": reminders}
    )


@router.post("/reminders/{reminder_id}/dismiss")
def dismiss_reminder(request: Request, reminder_id: int, db: Session = Depends(get_db)):
    reminder = db.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    reminder.dismissed_at = datetime.now(timezone.utc)
    db.commit()

    return templates.TemplateResponse(
        request, "reminders/_banner.html", {"reminders": _due_reminders(db)}
    )


@router.post("/reminders/{reminder_id}/snooze")
def snooze_reminder(
    request: Request, reminder_id: int, minutes: int = Form(15), db: Session = Depends(get_db)
):
    reminder = db.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    reminder.snoozed_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    db.commit()

    return templates.TemplateResponse(
        request, "reminders/_banner.html", {"reminders": _due_reminders(db)}
    )
```

`Reminder.task` requires a relationship back to `Task`. Add it to `idea_space/app/models.py`'s `Reminder` class:

```python
    task: Mapped["Task"] = relationship()
```

(Insert this line inside the `Reminder` class, after the `snoozed_until` column definition. `Task` is already defined above `Reminder` in the same module, so no new import is needed.)

- [ ] **Step 4: Write templates/reminders/_banner.html**

```html
<div id="reminder-banner" hx-get="/reminders/due" hx-trigger="every 30s" hx-swap="outerHTML">
  {% for reminder in reminders %}
  <div class="reminder" data-reminder-id="{{ reminder.id }}">
    <span>{{ reminder.task_title }}</span>
    <button hx-post="/reminders/{{ reminder.id }}/snooze" hx-vals='{"minutes": "15"}' hx-target="#reminder-banner" hx-swap="outerHTML">Snooze 15m</button>
    <button hx-post="/reminders/{{ reminder.id }}/dismiss" hx-target="#reminder-banner" hx-swap="outerHTML">Dismiss</button>
  </div>
  {% endfor %}
</div>
```

- [ ] **Step 5: Mount the banner in base.html and add remind_at to task creation**

Modify `idea_space/app/templates/base.html` — add inside `<body>`, before `<main>`:

```html
  <div hx-get="/reminders/due" hx-trigger="load" hx-swap="outerHTML" id="reminder-banner"></div>
  <main>{% block content %}{% endblock %}</main>
```

(Remove the old plain `<main>` line it replaces.)

Modify `idea_space/app/templates/tasks/_form.html` — add before the submit button:

```html
  <input type="datetime-local" name="remind_at" placeholder="Remind me at...">
```

Modify `idea_space/app/routers/tasks.py`'s `create_task` — add `remind_at: str | None = Form(None)` to the signature, and after `db.refresh(task)` (before the `if recurrence_pattern:` block):

```python
    if remind_at:
        from app.models import Reminder

        parsed_remind_at = datetime.fromisoformat(remind_at).replace(tzinfo=timezone.utc)
        db.add(Reminder(task_id=task.id, remind_at=parsed_remind_at))
        db.commit()
```

- [ ] **Step 6: Wire the router into main.py**

Modify `idea_space/app/main.py`: add `from app.routers import reminders` and `app.include_router(reminders.router)`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 8: Manual verification**

Run: `cd idea_space && uvicorn app.main:app --reload`, create a task with a `remind_at` a minute in the future, wait for it to become due, and confirm the banner appears within 30 seconds (the polling interval) and that Snooze/Dismiss remove it.

- [ ] **Step 9: Commit**

```bash
git add idea_space/app/routers/reminders.py idea_space/app/templates/reminders idea_space/app/templates/tasks/_form.html idea_space/app/templates/base.html idea_space/app/routers/tasks.py idea_space/app/models.py idea_space/app/main.py idea_space/tests/test_reminders.py
git commit -m "feat: add reminders with due-check polling, snooze, and dismiss"
```

---

## Plan Self-Review Notes

- **Spec coverage:** Recurring Tasks (Tasks 3, 4, 5, 6) · Calendar Planning (Tasks 7, 8) · Task Organization/Labels/Filtering (Tasks 9, 10) · Reminders (Task 11) · future-proofing via `workspace_id`/`owner_id` (Task 2) · UTC storage (Task 2 models) — all spec sections have a covering task.
- **Type consistency checked:** `compute_next_due_date` / `project_occurrences` signatures (Task 3) match their call sites in Task 5 (`complete_task`) and Task 7 (`calendar_week`). `_open_tasks`/`_filtered_tasks` naming is consistent from Task 4 through Task 10 (Task 10 replaces Task 4's `_open_tasks` body while keeping its name and call sites intact). `Reminder.task` relationship (added in Task 11) is consumed only within Task 11.
- **No placeholders:** every step includes complete, runnable code; no "TBD"/"similar to Task N" shortcuts.
