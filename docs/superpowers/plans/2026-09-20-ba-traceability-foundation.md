# Idea Space — BA Traceability Workspace Foundation (Slice 3a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the core BA entities (Requirement, Stakeholder, Decision, Risk), their many-to-many links to each other and to Task, a read-only traceability matrix, and app navigation to the existing Idea Space codebase.

**Architecture:** Four new SQLAlchemy models plus four junction tables, one FastAPI router per entity (mirroring the existing `labels.py` router's shape), a Requirement detail page with inline link-assignment forms, and a read-only matrix view. Entity management panels (Stakeholder/Decision/Risk create-edit-delete) live on the Requirements list page, mirroring how Slice 1's label manager lives on the Task list page.

**Tech Stack:** Same as Slices 1-2 — Python 3.11+, FastAPI, SQLAlchemy 2.0.54 (SQLite), Jinja2, htmx, pytest, httpx. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-20-ba-traceability-foundation-design.md`

## Global Constraints

- Every entity carries `workspace_id`, matching the future-proofing convention established since Slice 1.
- All four junction tables (`RequirementStakeholder`, `RequirementDecision`, `RequirementRisk`, `RequirementTask`) use the same composite-primary-key pattern as the existing `TaskLabel` table — no surrogate `id` column.
- Deleting a `Stakeholder`/`Decision`/`Risk` explicitly deletes its own junction rows first, then the row itself — never relies on an implicit cascade (this is the fix for the orphaned-join-row bug found in Slice 1's review, applied proactively here).
- Assigning an already-linked entity to a requirement is idempotent — no duplicate junction row, no error (same convention as Slice 1's label assignment).
- `Risk.severity`, `Risk.likelihood` (`"low"|"medium"|"high"`), `Risk.status` (`"open"|"mitigated"|"closed"`), and `Requirement.status` (`"draft"|"approved"|"in_progress"|"delivered"`) are validated on write, returning `400` for an invalid value.
- **Every htmx-targeted response renders a template whose root is exactly the single element being swapped — never a multi-sibling fragment, never a full page.** This is the fix for the full-page-duplication bug found and fixed in Slice 2's final review (commits `68a1e13`/`06d3b84` on the `history-follow-through` branch): htmx's `outerHTML` swap inserts *every* top-level node in the response, so a response with sibling elements outside the intended target duplicates those siblings on every interaction. Concretely: `requirements/_list_only.html`, `requirements/_page.html`, `stakeholders/_manager.html`, `decisions/_manager.html`, and `risks/_manager.html` are each a single root element, used only as htmx swap targets — never rendered as a page's `{% block content %}` body directly.
- Deleting a `Requirement` from its detail page uses the `HX-Redirect` response header (not an htmx swap) to navigate back to `/requirements`, since the delete button lives on a page that doesn't contain the list's `#requirement-list` element to swap into.
- Every task must leave the full test suite (`cd idea_space && python -m pytest tests/ -v`) passing with pristine output before committing.

---

## File Structure

```
idea_space/
  app/
    models.py                              # MODIFY: add 4 entities + 4 junction tables
    routers/
      stakeholders.py                      # CREATE
      decisions.py                         # CREATE
      risks.py                             # CREATE
      requirements.py                      # CREATE
      matrix.py                            # CREATE
      __init__.py                          # unchanged
    templates/
      base.html                            # MODIFY: add nav bar
      stakeholders/
        _manager.html                      # CREATE
      decisions/
        _manager.html                      # CREATE
      risks/
        _manager.html                      # CREATE
      requirements/
        list.html                          # CREATE
        _list_only.html                    # CREATE
        _row.html                          # CREATE
        detail.html                        # CREATE
        _page.html                         # CREATE
      matrix/
        index.html                         # CREATE
    static/
      app.css                              # MODIFY: styling for new entities + nav
  tests/
    test_ba_models.py                      # CREATE
    test_stakeholders.py                   # CREATE
    test_decisions.py                      # CREATE
    test_risks.py                          # CREATE
    test_requirements.py                   # CREATE
    test_matrix.py                         # CREATE
```

---

### Task 1: Data models — Requirement, Stakeholder, Decision, Risk, and junction tables

**Files:**
- Modify: `idea_space/app/models.py`
- Create: `idea_space/tests/test_ba_models.py`

**Interfaces:**
- Consumes: `app.db.Base`, `app.models.Task`, `app.seed.seed_default_workspace` (existing).
- Produces: `app.models.Stakeholder`, `app.models.Decision`, `app.models.Risk`, `app.models.Requirement` (with `.stakeholders`, `.decisions`, `.risks`, `.tasks` relationship attributes), and junction models `RequirementStakeholder`, `RequirementDecision`, `RequirementRisk`, `RequirementTask`.

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_ba_models.py`:

```python
from datetime import date, datetime, timezone

from app.models import Decision, Requirement, Risk, Stakeholder, Task
from app.seed import seed_default_workspace

UTC = timezone.utc


def test_stakeholder_has_expected_fields(db_session):
    workspace, _ = seed_default_workspace(db_session)
    stakeholder = Stakeholder(workspace_id=workspace.id, name="Jane Sponsor", role="Sponsor")
    db_session.add(stakeholder)
    db_session.commit()

    assert stakeholder.id is not None
    assert stakeholder.contact_info is None


def test_decision_has_expected_fields(db_session):
    workspace, _ = seed_default_workspace(db_session)
    decision = Decision(
        workspace_id=workspace.id,
        title="Use SSO for login",
        rationale="Reduces password reset burden",
        decided_at=date(2026, 9, 20),
        decided_by="Jane Sponsor",
    )
    db_session.add(decision)
    db_session.commit()

    assert decision.id is not None


def test_risk_defaults(db_session):
    workspace, _ = seed_default_workspace(db_session)
    risk = Risk(workspace_id=workspace.id, title="Vendor API instability", description="...")
    db_session.add(risk)
    db_session.commit()

    assert risk.severity == "medium"
    assert risk.likelihood == "medium"
    assert risk.status == "open"
    assert risk.mitigation is None


def test_requirement_defaults_and_links(db_session):
    workspace, user = seed_default_workspace(db_session)
    stakeholder = Stakeholder(workspace_id=workspace.id, name="Jane Sponsor", role="Sponsor")
    decision = Decision(
        workspace_id=workspace.id,
        title="Use SSO",
        rationale="",
        decided_at=date(2026, 9, 20),
        decided_by="Jane",
    )
    risk = Risk(workspace_id=workspace.id, title="Vendor risk", description="")
    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Implement SSO",
        due_date=datetime(2026, 9, 25, tzinfo=UTC),
    )
    db_session.add_all([stakeholder, decision, risk, task])
    db_session.commit()

    requirement = Requirement(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Users can log in with SSO",
        description="...",
        business_need="Reduce support tickets",
        acceptance_criteria="Given a corporate email, when...",
    )
    requirement.stakeholders.append(stakeholder)
    requirement.decisions.append(decision)
    requirement.risks.append(risk)
    requirement.tasks.append(task)
    db_session.add(requirement)
    db_session.commit()

    assert requirement.status == "draft"
    assert [s.name for s in requirement.stakeholders] == ["Jane Sponsor"]
    assert [d.title for d in requirement.decisions] == ["Use SSO"]
    assert [r.title for r in requirement.risks] == ["Vendor risk"]
    assert [t.title for t in requirement.tasks] == ["Implement SSO"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_ba_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Stakeholder' from 'app.models'`.

- [ ] **Step 3: Add the models**

Modify `idea_space/app/models.py` — change the top import line from:

```python
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
```

to:

```python
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
```

and change the first import line from:

```python
from datetime import datetime, timezone
```

to:

```python
from datetime import date, datetime, timezone
```

Append the following classes at the end of the file (after `ActivityLog`):

```python
class Stakeholder(Base):
    __tablename__ = "stakeholders"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(100))
    contact_info: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    title: Mapped[str] = mapped_column(String(255))
    rationale: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[date] = mapped_column(Date)
    decided_by: Mapped[str] = mapped_column(String(255))


class Risk(Base):
    __tablename__ = "risks"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    likelihood: Mapped[str] = mapped_column(String(20), default="medium")
    mitigation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")


class RequirementStakeholder(Base):
    __tablename__ = "requirement_stakeholders"

    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id"), primary_key=True)
    stakeholder_id: Mapped[int] = mapped_column(ForeignKey("stakeholders.id"), primary_key=True)


class RequirementDecision(Base):
    __tablename__ = "requirement_decisions"

    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id"), primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id"), primary_key=True)


class RequirementRisk(Base):
    __tablename__ = "requirement_risks"

    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id"), primary_key=True)
    risk_id: Mapped[int] = mapped_column(ForeignKey("risks.id"), primary_key=True)


class RequirementTask(Base):
    __tablename__ = "requirement_tasks"

    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id"), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), primary_key=True)


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    business_need: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    stakeholders: Mapped[list[Stakeholder]] = relationship(secondary="requirement_stakeholders")
    decisions: Mapped[list[Decision]] = relationship(secondary="requirement_decisions")
    risks: Mapped[list[Risk]] = relationship(secondary="requirement_risks")
    tasks: Mapped[list[Task]] = relationship(secondary="requirement_tasks")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (70 tests: 66 existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add idea_space/app/models.py idea_space/tests/test_ba_models.py
git commit -m "feat: add Requirement, Stakeholder, Decision, Risk models and their junction tables"
```

---

### Task 2: Stakeholder CRUD

**Files:**
- Create: `idea_space/app/routers/stakeholders.py`
- Create: `idea_space/app/templates/stakeholders/_manager.html`
- Modify: `idea_space/app/main.py` (include the router)
- Create: `idea_space/tests/test_stakeholders.py`

**Interfaces:**
- Consumes: `app.models.Stakeholder`, `app.models.RequirementStakeholder`, `app.models.Requirement` (Task 1), `app.seed.seed_default_workspace`.
- Produces: `POST /stakeholders`, `PATCH /stakeholders/{id}`, `DELETE /stakeholders/{id}` — each returns the `stakeholders/_manager.html` fragment (single root `<div id="stakeholder-manager">`) with `{"all_stakeholders": [...]}`.

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_stakeholders.py`:

```python
def test_create_stakeholder(client):
    response = client.post("/stakeholders", data={"name": "Jane Sponsor", "role": "Sponsor"})
    assert response.status_code == 200
    assert b"Jane Sponsor" in response.content


def test_edit_stakeholder(client, db_session):
    from app.models import Stakeholder

    client.post("/stakeholders", data={"name": "Jane Sponsor", "role": "Sponsor"})
    stakeholder = db_session.query(Stakeholder).filter_by(name="Jane Sponsor").one()

    response = client.patch(
        f"/stakeholders/{stakeholder.id}",
        data={"name": "Jane Smith", "role": "Executive Sponsor"},
    )
    assert response.status_code == 200
    assert b"Jane Smith" in response.content

    db_session.refresh(stakeholder)
    assert stakeholder.role == "Executive Sponsor"


def test_delete_stakeholder_removes_junction_rows(client, db_session):
    from app.models import Requirement, RequirementStakeholder, Stakeholder
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    stakeholder = Stakeholder(workspace_id=workspace.id, name="Jane Sponsor", role="Sponsor")
    db_session.add_all([requirement, stakeholder])
    db_session.commit()
    requirement.stakeholders.append(stakeholder)
    db_session.commit()

    response = client.delete(f"/stakeholders/{stakeholder.id}")
    assert response.status_code == 200

    db_session.expire_all()
    assert db_session.query(Stakeholder).filter_by(id=stakeholder.id).first() is None
    remaining = (
        db_session.query(RequirementStakeholder)
        .filter_by(stakeholder_id=stakeholder.id)
        .all()
    )
    assert remaining == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_stakeholders.py -v`
Expected: FAIL with `404 Not Found` for `POST /stakeholders`.

- [ ] **Step 3: Write app/routers/stakeholders.py**

```python
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
```

- [ ] **Step 4: Write templates/stakeholders/_manager.html**

```html
<div id="stakeholder-manager">
  <h3>Manage stakeholders</h3>
  <form hx-post="/stakeholders" hx-target="#stakeholder-manager" hx-swap="outerHTML">
    <input type="text" name="name" placeholder="Name" required>
    <input type="text" name="role" placeholder="Role" required>
    <input type="text" name="contact_info" placeholder="Contact info (optional)">
    <button type="submit">Add stakeholder</button>
  </form>
  <ul class="entity-manager-list">
    {% for stakeholder in all_stakeholders|default([]) %}
    <li>
      <span>{{ stakeholder.name }} ({{ stakeholder.role }})</span>
      <form hx-patch="/stakeholders/{{ stakeholder.id }}" hx-target="#stakeholder-manager" hx-swap="outerHTML" style="display:inline">
        <input type="text" name="name" value="{{ stakeholder.name }}" size="12">
        <input type="text" name="role" value="{{ stakeholder.role }}" size="10">
        <input type="text" name="contact_info" value="{{ stakeholder.contact_info or '' }}" size="12">
        <button type="submit">Save</button>
      </form>
      <button hx-delete="/stakeholders/{{ stakeholder.id }}" hx-target="#stakeholder-manager" hx-swap="outerHTML">Delete</button>
    </li>
    {% endfor %}
  </ul>
</div>
```

- [ ] **Step 5: Wire the router into main.py**

Modify `idea_space/app/main.py` — change:

```python
from app.routers import calendar, labels, reminders, tasks
```

to:

```python
from app.routers import calendar, labels, reminders, stakeholders, tasks
```

and add `app.include_router(stakeholders.router)` alongside the existing `app.include_router(...)` lines.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (73 tests).

- [ ] **Step 7: Commit**

```bash
git add idea_space/app/routers/stakeholders.py idea_space/app/templates/stakeholders/_manager.html idea_space/app/main.py idea_space/tests/test_stakeholders.py
git commit -m "feat: add stakeholder CRUD"
```

---

### Task 3: Decision CRUD

**Files:**
- Create: `idea_space/app/routers/decisions.py`
- Create: `idea_space/app/templates/decisions/_manager.html`
- Modify: `idea_space/app/main.py` (include the router)
- Create: `idea_space/tests/test_decisions.py`

**Interfaces:**
- Consumes: `app.models.Decision`, `app.models.RequirementDecision` (Task 1).
- Produces: `POST /decisions`, `PATCH /decisions/{id}`, `DELETE /decisions/{id}` — each returns `decisions/_manager.html` (single root `<div id="decision-manager">`) with `{"all_decisions": [...]}`.

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_decisions.py`:

```python
def test_create_decision(client):
    response = client.post(
        "/decisions",
        data={
            "title": "Use SSO",
            "rationale": "Reduces password reset burden",
            "decided_at": "2026-09-20",
            "decided_by": "Jane Sponsor",
        },
    )
    assert response.status_code == 200
    assert b"Use SSO" in response.content


def test_edit_decision(client, db_session):
    from app.models import Decision

    client.post(
        "/decisions",
        data={"title": "Use SSO", "rationale": "", "decided_at": "2026-09-20", "decided_by": "Jane"},
    )
    decision = db_session.query(Decision).filter_by(title="Use SSO").one()

    response = client.patch(
        f"/decisions/{decision.id}",
        data={
            "title": "Use SSO for all logins",
            "rationale": "Updated rationale",
            "decided_at": "2026-09-21",
            "decided_by": "Jane Sponsor",
        },
    )
    assert response.status_code == 200
    assert b"Use SSO for all logins" in response.content

    db_session.refresh(decision)
    assert decision.rationale == "Updated rationale"


def test_delete_decision_removes_junction_rows(client, db_session):
    from datetime import date

    from app.models import Decision, Requirement, RequirementDecision
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    decision = Decision(
        workspace_id=workspace.id,
        title="Use SSO",
        rationale="",
        decided_at=date(2026, 9, 20),
        decided_by="Jane",
    )
    db_session.add_all([requirement, decision])
    db_session.commit()
    requirement.decisions.append(decision)
    db_session.commit()

    response = client.delete(f"/decisions/{decision.id}")
    assert response.status_code == 200

    db_session.expire_all()
    assert db_session.query(Decision).filter_by(id=decision.id).first() is None
    remaining = (
        db_session.query(RequirementDecision).filter_by(decision_id=decision.id).all()
    )
    assert remaining == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_decisions.py -v`
Expected: FAIL with `404 Not Found` for `POST /decisions`.

- [ ] **Step 3: Write app/routers/decisions.py**

```python
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
```

- [ ] **Step 4: Write templates/decisions/_manager.html**

```html
<div id="decision-manager">
  <h3>Manage decisions</h3>
  <form hx-post="/decisions" hx-target="#decision-manager" hx-swap="outerHTML">
    <input type="text" name="title" placeholder="Decision title" required>
    <input type="text" name="rationale" placeholder="Rationale">
    <input type="date" name="decided_at" required>
    <input type="text" name="decided_by" placeholder="Decided by" required>
    <button type="submit">Add decision</button>
  </form>
  <ul class="entity-manager-list">
    {% for decision in all_decisions|default([]) %}
    <li>
      <span>{{ decision.title }} — {{ decision.decided_at }} by {{ decision.decided_by }}</span>
      <form hx-patch="/decisions/{{ decision.id }}" hx-target="#decision-manager" hx-swap="outerHTML" style="display:inline">
        <input type="text" name="title" value="{{ decision.title }}" size="12">
        <input type="text" name="rationale" value="{{ decision.rationale }}" size="12">
        <input type="date" name="decided_at" value="{{ decision.decided_at }}">
        <input type="text" name="decided_by" value="{{ decision.decided_by }}" size="10">
        <button type="submit">Save</button>
      </form>
      <button hx-delete="/decisions/{{ decision.id }}" hx-target="#decision-manager" hx-swap="outerHTML">Delete</button>
    </li>
    {% endfor %}
  </ul>
</div>
```

- [ ] **Step 5: Wire the router into main.py**

Modify `idea_space/app/main.py` — change:

```python
from app.routers import calendar, labels, reminders, stakeholders, tasks
```

to:

```python
from app.routers import calendar, decisions, labels, reminders, stakeholders, tasks
```

and add `app.include_router(decisions.router)` alongside the existing includes.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (76 tests).

- [ ] **Step 7: Commit**

```bash
git add idea_space/app/routers/decisions.py idea_space/app/templates/decisions/_manager.html idea_space/app/main.py idea_space/tests/test_decisions.py
git commit -m "feat: add decision CRUD"
```

---

### Task 4: Risk CRUD with severity/likelihood/status validation

**Files:**
- Create: `idea_space/app/routers/risks.py`
- Create: `idea_space/app/templates/risks/_manager.html`
- Modify: `idea_space/app/main.py` (include the router)
- Create: `idea_space/tests/test_risks.py`

**Interfaces:**
- Consumes: `app.models.Risk`, `app.models.RequirementRisk` (Task 1).
- Produces: `POST /risks`, `PATCH /risks/{id}`, `DELETE /risks/{id}` — each returns `risks/_manager.html` (single root `<div id="risk-manager">`) with `{"all_risks": [...]}`. `POST`/`PATCH` return `400` for an invalid `severity`, `likelihood`, or `status`.

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_risks.py`:

```python
def test_create_risk(client):
    response = client.post(
        "/risks",
        data={"title": "Vendor API instability", "description": "...", "severity": "high", "likelihood": "medium"},
    )
    assert response.status_code == 200
    assert b"Vendor API instability" in response.content


def test_create_risk_rejects_invalid_severity(client):
    response = client.post(
        "/risks", data={"title": "Bad risk", "severity": "extreme", "likelihood": "medium"}
    )
    assert response.status_code == 400


def test_create_risk_rejects_invalid_status(client):
    response = client.post(
        "/risks",
        data={"title": "Bad risk", "severity": "high", "likelihood": "medium", "status": "ignored"},
    )
    assert response.status_code == 400


def test_edit_risk(client, db_session):
    from app.models import Risk

    client.post("/risks", data={"title": "Vendor risk", "severity": "high", "likelihood": "medium"})
    risk = db_session.query(Risk).filter_by(title="Vendor risk").one()

    response = client.patch(
        f"/risks/{risk.id}",
        data={
            "title": "Vendor risk",
            "severity": "low",
            "likelihood": "low",
            "status": "mitigated",
            "mitigation": "Switched vendors",
        },
    )
    assert response.status_code == 200

    db_session.refresh(risk)
    assert risk.status == "mitigated"
    assert risk.mitigation == "Switched vendors"


def test_delete_risk_removes_junction_rows(client, db_session):
    from app.models import Requirement, RequirementRisk, Risk
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    risk = Risk(workspace_id=workspace.id, title="Vendor risk", description="")
    db_session.add_all([requirement, risk])
    db_session.commit()
    requirement.risks.append(risk)
    db_session.commit()

    response = client.delete(f"/risks/{risk.id}")
    assert response.status_code == 200

    db_session.expire_all()
    assert db_session.query(Risk).filter_by(id=risk.id).first() is None
    remaining = db_session.query(RequirementRisk).filter_by(risk_id=risk.id).all()
    assert remaining == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_risks.py -v`
Expected: FAIL with `404 Not Found` for `POST /risks`.

- [ ] **Step 3: Write app/routers/risks.py**

```python
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
```

- [ ] **Step 4: Write templates/risks/_manager.html**

```html
<div id="risk-manager">
  <h3>Manage risks</h3>
  <form hx-post="/risks" hx-target="#risk-manager" hx-swap="outerHTML">
    <input type="text" name="title" placeholder="Risk title" required>
    <input type="text" name="description" placeholder="Description">
    <select name="severity">
      <option value="low">Low</option>
      <option value="medium" selected>Medium</option>
      <option value="high">High</option>
    </select>
    <select name="likelihood">
      <option value="low">Low</option>
      <option value="medium" selected>Medium</option>
      <option value="high">High</option>
    </select>
    <select name="status">
      <option value="open" selected>Open</option>
      <option value="mitigated">Mitigated</option>
      <option value="closed">Closed</option>
    </select>
    <button type="submit">Add risk</button>
  </form>
  <ul class="entity-manager-list">
    {% for risk in all_risks|default([]) %}
    <li>
      <span>{{ risk.title }} ({{ risk.severity }}/{{ risk.likelihood }}, {{ risk.status }})</span>
      <form hx-patch="/risks/{{ risk.id }}" hx-target="#risk-manager" hx-swap="outerHTML" style="display:inline">
        <input type="text" name="title" value="{{ risk.title }}" size="12">
        <select name="severity">
          <option value="low" {% if risk.severity == "low" %}selected{% endif %}>Low</option>
          <option value="medium" {% if risk.severity == "medium" %}selected{% endif %}>Medium</option>
          <option value="high" {% if risk.severity == "high" %}selected{% endif %}>High</option>
        </select>
        <select name="likelihood">
          <option value="low" {% if risk.likelihood == "low" %}selected{% endif %}>Low</option>
          <option value="medium" {% if risk.likelihood == "medium" %}selected{% endif %}>Medium</option>
          <option value="high" {% if risk.likelihood == "high" %}selected{% endif %}>High</option>
        </select>
        <select name="status">
          <option value="open" {% if risk.status == "open" %}selected{% endif %}>Open</option>
          <option value="mitigated" {% if risk.status == "mitigated" %}selected{% endif %}>Mitigated</option>
          <option value="closed" {% if risk.status == "closed" %}selected{% endif %}>Closed</option>
        </select>
        <button type="submit">Save</button>
      </form>
      <button hx-delete="/risks/{{ risk.id }}" hx-target="#risk-manager" hx-swap="outerHTML">Delete</button>
    </li>
    {% endfor %}
  </ul>
</div>
```

- [ ] **Step 5: Wire the router into main.py**

Modify `idea_space/app/main.py` — change:

```python
from app.routers import calendar, decisions, labels, reminders, stakeholders, tasks
```

to:

```python
from app.routers import calendar, decisions, labels, reminders, risks, stakeholders, tasks
```

and add `app.include_router(risks.router)` alongside the existing includes.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (81 tests).

- [ ] **Step 7: Commit**

```bash
git add idea_space/app/routers/risks.py idea_space/app/templates/risks/_manager.html idea_space/app/main.py idea_space/tests/test_risks.py
git commit -m "feat: add risk CRUD with severity/likelihood/status validation"
```

---

### Task 5: Requirement CRUD, list page, and detail page

**Files:**
- Create: `idea_space/app/routers/requirements.py`
- Create: `idea_space/app/templates/requirements/list.html`
- Create: `idea_space/app/templates/requirements/_list_only.html`
- Create: `idea_space/app/templates/requirements/_row.html`
- Create: `idea_space/app/templates/requirements/detail.html`
- Create: `idea_space/app/templates/requirements/_page.html`
- Modify: `idea_space/app/main.py` (include the router)
- Create: `idea_space/tests/test_requirements.py`

**Interfaces:**
- Consumes: `app.models.Requirement`, `Stakeholder`, `Decision`, `Risk`, `Task`, and all four junction models (Task 1); `stakeholders/_manager.html`, `decisions/_manager.html`, `risks/_manager.html` (Tasks 2-4, included in `list.html`).
- Produces: `GET /requirements` (list page), `POST /requirements` (create), `GET /requirements/{id}` (detail page), `PATCH /requirements/{id}` (edit), `DELETE /requirements/{id}` (delete, `HX-Redirect: /requirements`). Also produces `_requirement_page_context(db, requirement) -> dict` — a module-level helper Task 6's link endpoints will reuse (not a public interface outside this router, but its name/shape matters for Task 6).

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_requirements.py`:

```python
def test_get_requirements_returns_empty_list_page(client):
    response = client.get("/requirements")
    assert response.status_code == 200
    assert b"No requirements yet" in response.content


def test_create_requirement_returns_it_in_list(client):
    response = client.post(
        "/requirements",
        data={
            "title": "Users can log in with SSO",
            "description": "...",
            "business_need": "Reduce support tickets",
            "acceptance_criteria": "Given a corporate email, when...",
            "status": "draft",
        },
    )
    assert response.status_code == 200
    assert b"Users can log in with SSO" in response.content


def test_requirement_detail_page_renders(client, db_session):
    from app.models import Requirement
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    response = client.get(f"/requirements/{requirement.id}")
    assert response.status_code == 200
    assert b"Req 1" in response.content


def test_requirement_detail_unknown_id_returns_404(client):
    response = client.get("/requirements/999")
    assert response.status_code == 404


def test_edit_requirement(client, db_session):
    from app.models import Requirement
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    response = client.patch(
        f"/requirements/{requirement.id}",
        data={
            "title": "Req 1 Updated",
            "description": "",
            "business_need": "",
            "acceptance_criteria": "",
            "status": "approved",
        },
    )
    assert response.status_code == 200
    assert b"Req 1 Updated" in response.content

    db_session.refresh(requirement)
    assert requirement.status == "approved"


def test_edit_requirement_rejects_invalid_status(client, db_session):
    from app.models import Requirement
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    response = client.patch(
        f"/requirements/{requirement.id}",
        data={"title": "Req 1", "status": "banana"},
    )
    assert response.status_code == 400


def test_delete_requirement_redirects_and_cleans_all_junctions(client, db_session):
    from datetime import date, datetime, timezone

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

    UTC = timezone.utc
    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    stakeholder = Stakeholder(workspace_id=workspace.id, name="Jane", role="Sponsor")
    decision = Decision(
        workspace_id=workspace.id, title="Dec 1", rationale="", decided_at=date(2026, 9, 20), decided_by="Jane"
    )
    risk = Risk(workspace_id=workspace.id, title="Risk 1", description="")
    task = Task(
        workspace_id=workspace.id, owner_id=user.id, title="Task 1", due_date=datetime(2026, 9, 25, tzinfo=UTC)
    )
    db_session.add_all([requirement, stakeholder, decision, risk, task])
    db_session.commit()
    requirement.stakeholders.append(stakeholder)
    requirement.decisions.append(decision)
    requirement.risks.append(risk)
    requirement.tasks.append(task)
    db_session.commit()

    response = client.delete(f"/requirements/{requirement.id}", follow_redirects=False)
    assert response.status_code == 200
    assert response.headers.get("hx-redirect") == "/requirements"

    db_session.expire_all()
    assert db_session.query(Requirement).filter_by(id=requirement.id).first() is None
    assert db_session.query(RequirementStakeholder).filter_by(requirement_id=requirement.id).all() == []
    assert db_session.query(RequirementDecision).filter_by(requirement_id=requirement.id).all() == []
    assert db_session.query(RequirementRisk).filter_by(requirement_id=requirement.id).all() == []
    assert db_session.query(RequirementTask).filter_by(requirement_id=requirement.id).all() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_requirements.py -v`
Expected: FAIL with `404 Not Found` for `GET /requirements`.

- [ ] **Step 3: Write app/routers/requirements.py**

```python
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
```

- [ ] **Step 4: Write templates/requirements/_row.html**

```html
<li class="requirement" data-requirement-id="{{ requirement.id }}">
  <a href="/requirements/{{ requirement.id }}" class="requirement-title">{{ requirement.title }}</a>
  <span class="requirement-status">{{ requirement.status }}</span>
</li>
```

- [ ] **Step 5: Write templates/requirements/_list_only.html**

```html
<ul id="requirement-list">
  {% if not requirements %}
  <p>No requirements yet — add one above.</p>
  {% else %}
  {% for requirement in requirements %}
    {% include "requirements/_row.html" %}
  {% endfor %}
  {% endif %}
</ul>
```

- [ ] **Step 6: Write templates/requirements/list.html**

```html
{% extends "base.html" %}
{% block content %}
<h2>Requirements</h2>
<form hx-post="/requirements" hx-target="#requirement-list" hx-swap="outerHTML">
  <input type="text" name="title" placeholder="Requirement title" required>
  <textarea name="description" placeholder="Description"></textarea>
  <textarea name="business_need" placeholder="Business need"></textarea>
  <textarea name="acceptance_criteria" placeholder="Acceptance criteria"></textarea>
  <select name="status">
    <option value="draft">Draft</option>
    <option value="approved">Approved</option>
    <option value="in_progress">In Progress</option>
    <option value="delivered">Delivered</option>
  </select>
  <button type="submit">Add requirement</button>
</form>
{% include "stakeholders/_manager.html" %}
{% include "decisions/_manager.html" %}
{% include "risks/_manager.html" %}
{% include "requirements/_list_only.html" %}
{% endblock %}
```

- [ ] **Step 7: Write templates/requirements/_page.html**

```html
<div id="requirement-page">
  <h2>{{ requirement.title }}</h2>
  <form hx-patch="/requirements/{{ requirement.id }}" hx-target="#requirement-page" hx-swap="outerHTML">
    <input type="text" name="title" value="{{ requirement.title }}" required>
    <textarea name="description">{{ requirement.description }}</textarea>
    <textarea name="business_need">{{ requirement.business_need }}</textarea>
    <textarea name="acceptance_criteria">{{ requirement.acceptance_criteria }}</textarea>
    <select name="status">
      <option value="draft" {% if requirement.status == "draft" %}selected{% endif %}>Draft</option>
      <option value="approved" {% if requirement.status == "approved" %}selected{% endif %}>Approved</option>
      <option value="in_progress" {% if requirement.status == "in_progress" %}selected{% endif %}>In Progress</option>
      <option value="delivered" {% if requirement.status == "delivered" %}selected{% endif %}>Delivered</option>
    </select>
    <button type="submit">Save</button>
  </form>
  <button hx-delete="/requirements/{{ requirement.id }}">Delete requirement</button>

  <section>
    <h3>Stakeholders</h3>
    <ul>
      {% for stakeholder in requirement.stakeholders %}
      <li>{{ stakeholder.name }} ({{ stakeholder.role }})</li>
      {% endfor %}
    </ul>
    <form hx-post="/requirements/{{ requirement.id }}/stakeholders" hx-target="#requirement-page" hx-swap="outerHTML">
      <select name="stakeholder_id">
        {% for stakeholder in all_stakeholders %}
        <option value="{{ stakeholder.id }}">{{ stakeholder.name }}</option>
        {% endfor %}
      </select>
      <button type="submit">Link stakeholder</button>
    </form>
  </section>

  <section>
    <h3>Decisions</h3>
    <ul>
      {% for decision in requirement.decisions %}
      <li>{{ decision.title }}</li>
      {% endfor %}
    </ul>
    <form hx-post="/requirements/{{ requirement.id }}/decisions" hx-target="#requirement-page" hx-swap="outerHTML">
      <select name="decision_id">
        {% for decision in all_decisions %}
        <option value="{{ decision.id }}">{{ decision.title }}</option>
        {% endfor %}
      </select>
      <button type="submit">Link decision</button>
    </form>
  </section>

  <section>
    <h3>Risks</h3>
    <ul>
      {% for risk in requirement.risks %}
      <li>{{ risk.title }} ({{ risk.severity }}/{{ risk.likelihood }})</li>
      {% endfor %}
    </ul>
    <form hx-post="/requirements/{{ requirement.id }}/risks" hx-target="#requirement-page" hx-swap="outerHTML">
      <select name="risk_id">
        {% for risk in all_risks %}
        <option value="{{ risk.id }}">{{ risk.title }}</option>
        {% endfor %}
      </select>
      <button type="submit">Link risk</button>
    </form>
  </section>

  <section>
    <h3>Tasks</h3>
    <ul>
      {% for task in requirement.tasks %}
      <li>{{ task.title }}</li>
      {% endfor %}
    </ul>
    <form hx-post="/requirements/{{ requirement.id }}/tasks" hx-target="#requirement-page" hx-swap="outerHTML">
      <select name="task_id">
        {% for task in all_tasks %}
        <option value="{{ task.id }}">{{ task.title }}</option>
        {% endfor %}
      </select>
      <button type="submit">Link task</button>
    </form>
  </section>
</div>
```

Note: the "Link stakeholder/decision/risk/task" forms POST to endpoints that don't exist until Task 6 — that's expected. They will 404 if clicked before Task 6 lands; this task's own tests never click them (only Task 6's tests do, once the endpoints exist).

- [ ] **Step 8: Write templates/requirements/detail.html**

```html
{% extends "base.html" %}
{% block content %}
<a href="/requirements">&larr; Back to requirements</a>
{% include "requirements/_page.html" %}
{% endblock %}
```

- [ ] **Step 9: Wire the router into main.py**

Modify `idea_space/app/main.py` — change:

```python
from app.routers import calendar, decisions, labels, reminders, risks, stakeholders, tasks
```

to:

```python
from app.routers import calendar, decisions, labels, reminders, requirements, risks, stakeholders, tasks
```

and add `app.include_router(requirements.router)` alongside the existing includes.

- [ ] **Step 10: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (88 tests: 81 existing + 7 new).

- [ ] **Step 11: Commit**

```bash
git add idea_space/app/routers/requirements.py idea_space/app/templates/requirements idea_space/app/main.py idea_space/tests/test_requirements.py
git commit -m "feat: add requirement CRUD, list page, and detail page"
```

---

### Task 6: Link stakeholders, decisions, risks, and tasks to a requirement

**Files:**
- Modify: `idea_space/app/routers/requirements.py`
- Modify: `idea_space/tests/test_requirements.py`

**Interfaces:**
- Consumes: `_requirement_page_context` (Task 5), the many-to-many relationship attributes on `Requirement` (Task 1).
- Produces: `POST /requirements/{id}/stakeholders` (form: `stakeholder_id`), `POST /requirements/{id}/decisions` (form: `decision_id`), `POST /requirements/{id}/risks` (form: `risk_id`), `POST /requirements/{id}/tasks` (form: `task_id`) — each idempotently appends to the relevant relationship and returns `requirements/_page.html`.

- [ ] **Step 1: Write the failing test**

Append to `idea_space/tests/test_requirements.py`:

```python
def test_link_stakeholder_to_requirement(client, db_session):
    from app.models import Requirement, Stakeholder
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    client.post("/stakeholders", data={"name": "Jane Sponsor", "role": "Sponsor"})
    stakeholder = db_session.query(Stakeholder).filter_by(name="Jane Sponsor").one()

    response = client.post(
        f"/requirements/{requirement.id}/stakeholders", data={"stakeholder_id": stakeholder.id}
    )
    assert response.status_code == 200
    assert b"Jane Sponsor" in response.content

    db_session.refresh(requirement)
    assert [s.name for s in requirement.stakeholders] == ["Jane Sponsor"]


def test_link_stakeholder_is_idempotent(client, db_session):
    from app.models import Requirement, Stakeholder
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    client.post("/stakeholders", data={"name": "Jane Sponsor", "role": "Sponsor"})
    stakeholder = db_session.query(Stakeholder).filter_by(name="Jane Sponsor").one()

    client.post(f"/requirements/{requirement.id}/stakeholders", data={"stakeholder_id": stakeholder.id})
    client.post(f"/requirements/{requirement.id}/stakeholders", data={"stakeholder_id": stakeholder.id})

    db_session.refresh(requirement)
    assert len(requirement.stakeholders) == 1


def test_link_decision_to_requirement(client, db_session):
    from app.models import Decision, Requirement
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    client.post(
        "/decisions",
        data={"title": "Use SSO", "rationale": "", "decided_at": "2026-09-20", "decided_by": "Jane"},
    )
    decision = db_session.query(Decision).filter_by(title="Use SSO").one()

    response = client.post(f"/requirements/{requirement.id}/decisions", data={"decision_id": decision.id})
    assert response.status_code == 200
    assert b"Use SSO" in response.content


def test_link_risk_to_requirement(client, db_session):
    from app.models import Requirement, Risk
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    client.post("/risks", data={"title": "Vendor risk", "severity": "high", "likelihood": "medium"})
    risk = db_session.query(Risk).filter_by(title="Vendor risk").one()

    response = client.post(f"/requirements/{requirement.id}/risks", data={"risk_id": risk.id})
    assert response.status_code == 200
    assert b"Vendor risk" in response.content


def test_link_task_to_requirement(client, db_session):
    from datetime import datetime, timezone

    from app.models import Requirement, Task
    from app.seed import seed_default_workspace

    UTC = timezone.utc
    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    due = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Implement SSO", "due_date": due})
    task = db_session.query(Task).filter_by(title="Implement SSO").one()

    response = client.post(f"/requirements/{requirement.id}/tasks", data={"task_id": task.id})
    assert response.status_code == 200
    assert b"Implement SSO" in response.content


def test_link_stakeholder_unknown_requirement_returns_404(client, db_session):
    from app.models import Stakeholder

    client.post("/stakeholders", data={"name": "Jane Sponsor", "role": "Sponsor"})
    stakeholder = db_session.query(Stakeholder).filter_by(name="Jane Sponsor").one()

    response = client.post("/requirements/999/stakeholders", data={"stakeholder_id": stakeholder.id})
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_requirements.py -v`
Expected: FAIL with `404 Not Found` for `POST /requirements/{id}/stakeholders`.

- [ ] **Step 3: Add the four link endpoints**

Append to `idea_space/app/routers/requirements.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (94 tests: 88 existing + 6 new).

- [ ] **Step 5: Commit**

```bash
git add idea_space/app/routers/requirements.py idea_space/tests/test_requirements.py
git commit -m "feat: link stakeholders, decisions, risks, and tasks to a requirement"
```

---

### Task 7: Traceability matrix view

**Files:**
- Create: `idea_space/app/routers/matrix.py`
- Create: `idea_space/app/templates/matrix/index.html`
- Modify: `idea_space/app/main.py` (include the router)
- Create: `idea_space/tests/test_matrix.py`

**Interfaces:**
- Consumes: `app.models.Requirement` and its `.stakeholders`/`.decisions`/`.risks`/`.tasks` relationships (Task 1).
- Produces: `GET /matrix` — one row per requirement, columns showing linked stakeholder names / decision titles / risk titles / task titles, joined by `", "`, or an empty-state placeholder (`<span class="matrix-empty">—</span>`) per column when nothing is linked.

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_matrix.py`:

```python
def test_matrix_shows_linked_entities(client, db_session):
    from datetime import date, datetime, timezone

    from app.models import Decision, Requirement, Risk, Stakeholder, Task
    from app.seed import seed_default_workspace

    UTC = timezone.utc
    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req with links")
    stakeholder = Stakeholder(workspace_id=workspace.id, name="Jane Sponsor", role="Sponsor")
    decision = Decision(
        workspace_id=workspace.id, title="Use SSO", rationale="", decided_at=date(2026, 9, 20), decided_by="Jane"
    )
    risk = Risk(workspace_id=workspace.id, title="Vendor risk", description="")
    task = Task(
        workspace_id=workspace.id, owner_id=user.id, title="Implement SSO",
        due_date=datetime(2026, 9, 25, tzinfo=UTC),
    )
    db_session.add_all([requirement, stakeholder, decision, risk, task])
    db_session.commit()
    requirement.stakeholders.append(stakeholder)
    requirement.decisions.append(decision)
    requirement.risks.append(risk)
    requirement.tasks.append(task)
    db_session.commit()

    response = client.get("/matrix")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Req with links" in body
    assert "Jane Sponsor" in body
    assert "Use SSO" in body
    assert "Vendor risk" in body
    assert "Implement SSO" in body


def test_matrix_shows_empty_state_for_unlinked_requirement(client, db_session):
    from app.models import Requirement
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Lonely req")
    db_session.add(requirement)
    db_session.commit()

    response = client.get("/matrix")
    assert response.status_code == 200
    assert b"Lonely req" in response.content
    assert response.content.count(b"matrix-empty") == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_matrix.py -v`
Expected: FAIL with `404 Not Found` for `GET /matrix`.

- [ ] **Step 3: Write app/routers/matrix.py**

```python
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
```

- [ ] **Step 4: Write templates/matrix/index.html**

```html
{% extends "base.html" %}
{% block content %}
<h2>Traceability Matrix</h2>
{% if not requirements %}
<p>No requirements yet.</p>
{% else %}
<table class="matrix-table">
  <thead>
    <tr>
      <th>Requirement</th>
      <th>Stakeholders</th>
      <th>Decisions</th>
      <th>Risks</th>
      <th>Tasks</th>
    </tr>
  </thead>
  <tbody>
    {% for requirement in requirements %}
    <tr>
      <td><a href="/requirements/{{ requirement.id }}">{{ requirement.title }}</a></td>
      <td>
        {% if requirement.stakeholders %}
          {{ requirement.stakeholders | map(attribute='name') | join(', ') }}
        {% else %}
          <span class="matrix-empty">—</span>
        {% endif %}
      </td>
      <td>
        {% if requirement.decisions %}
          {{ requirement.decisions | map(attribute='title') | join(', ') }}
        {% else %}
          <span class="matrix-empty">—</span>
        {% endif %}
      </td>
      <td>
        {% if requirement.risks %}
          {{ requirement.risks | map(attribute='title') | join(', ') }}
        {% else %}
          <span class="matrix-empty">—</span>
        {% endif %}
      </td>
      <td>
        {% if requirement.tasks %}
          {{ requirement.tasks | map(attribute='title') | join(', ') }}
        {% else %}
          <span class="matrix-empty">—</span>
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Wire the router into main.py**

Modify `idea_space/app/main.py` — change:

```python
from app.routers import calendar, decisions, labels, reminders, requirements, risks, stakeholders, tasks
```

to:

```python
from app.routers import calendar, decisions, labels, matrix, reminders, requirements, risks, stakeholders, tasks
```

and add `app.include_router(matrix.router)` alongside the existing includes.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (96 tests: 94 existing + 2 new).

- [ ] **Step 7: Commit**

```bash
git add idea_space/app/routers/matrix.py idea_space/app/templates/matrix idea_space/app/main.py idea_space/tests/test_matrix.py
git commit -m "feat: add read-only traceability matrix view"
```

---

### Task 8: Navigation bar, SOL styling for new entities, and manual verification

**Files:**
- Modify: `idea_space/app/templates/base.html`
- Modify: `idea_space/app/static/app.css`
- Create: `idea_space/tests/test_navigation.py`

**Interfaces:**
- Consumes: SOL tokens already defined in `app.css`'s `:root` (Slice 2) — no new tokens needed, only new component rules using existing custom properties.
- Produces: a `<nav class="main-nav">` in `base.html` with links to `/tasks`, `/calendar`, `/requirements`, `/matrix`, styled consistently with the rest of the app.

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_navigation.py`:

```python
def test_main_nav_present_on_tasks_page(client):
    response = client.get("/tasks")
    assert response.status_code == 200
    assert b'class="main-nav"' in response.content
    assert b'href="/requirements"' in response.content
    assert b'href="/matrix"' in response.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_navigation.py -v`
Expected: FAIL — no `main-nav` class exists yet in `base.html`.

- [ ] **Step 3: Add the nav bar to base.html**

Replace the full contents of `idea_space/app/templates/base.html`:

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
  <header class="app-header">
    <h1>Idea Space</h1>
    <nav class="main-nav">
      <a href="/tasks">Tasks</a>
      <a href="/calendar">Calendar</a>
      <a href="/requirements">Requirements</a>
      <a href="/matrix">Matrix</a>
    </nav>
  </header>
  <div hx-get="/reminders/due" hx-trigger="load" hx-swap="outerHTML" id="reminder-banner"></div>
  <main>{% block content %}{% endblock %}</main>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Add styling for the nav and new entities**

Append to `idea_space/app/static/app.css`:

```css
.main-nav {
  display: flex;
  gap: var(--space-md);
  margin-top: var(--space-xs);
}

.main-nav a {
  font-size: var(--font-size-label);
  font-weight: 700;
  color: var(--color-ink-500);
  text-decoration: none;
}

.main-nav a:hover {
  color: var(--color-primary);
}

.entity-manager-list {
  list-style: none;
  padding: 0;
  margin: var(--space-sm) 0 0 0;
}

.entity-manager-list li {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xs) 0;
  border-bottom: 1px solid var(--color-line);
}

#requirement-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.requirement {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-xs);
  background: var(--color-surface-white);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
}

.requirement-status {
  font-size: var(--font-size-caption);
  color: var(--color-ink-500);
  text-transform: uppercase;
}

.matrix-table {
  width: 100%;
  border-collapse: collapse;
}

.matrix-table th, .matrix-table td {
  border: 1px solid var(--color-line);
  padding: var(--space-sm);
  text-align: left;
  font-size: var(--font-size-body);
}

.matrix-table th {
  background: var(--color-surface-container-low);
}

.matrix-empty {
  color: var(--color-ink-300);
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (97 tests: 96 existing + 1 new).

- [ ] **Step 6: Commit the code changes**

```bash
git add idea_space/app/templates/base.html idea_space/app/static/app.css idea_space/tests/test_navigation.py
git commit -m "feat: add main navigation bar and SOL styling for BA entities"
```

- [ ] **Step 7: Start the dev server against a fresh database**

Run: `cd idea_space && rm -f idea_space.db && python -m uvicorn app.main:app --port 8420` (run in the background; leave it running for the remaining steps).

- [ ] **Step 8: Seed representative data and verify each view in a browser**

```bash
curl -s -X POST http://127.0.0.1:8420/stakeholders -d "name=Jane+Sponsor" -d "role=Sponsor" > /dev/null
curl -s -X POST http://127.0.0.1:8420/decisions -d "title=Use+SSO" -d "rationale=Reduces+support+load" -d "decided_at=2026-09-20" -d "decided_by=Jane+Sponsor" > /dev/null
curl -s -X POST http://127.0.0.1:8420/risks -d "title=Vendor+API+instability" -d "severity=high" -d "likelihood=medium" > /dev/null
curl -s -X POST http://127.0.0.1:8420/requirements -d "title=Users+can+log+in+with+SSO" -d "business_need=Reduce+support+tickets" -d "status=draft" > /dev/null
```

Navigate to and screenshot: `http://127.0.0.1:8420/requirements` (confirm the create form, the three manager panels, and the new requirement all render with SOL styling — bordered cards, blue primary buttons, consistent with the existing Tasks page); click into the requirement's detail page and link the seeded stakeholder, decision, and risk to it via the inline forms, confirming each link appears immediately and no page-duplication occurs (per the Global Constraints' htmx-fragment rule — click each "Link X" button and confirm exactly one copy of the page renders, not two); navigate to `http://127.0.0.1:8420/matrix` and confirm the requirement's row shows the linked stakeholder/decision/risk names and an empty-state dash in the Tasks column; confirm the nav bar (Tasks / Calendar / Requirements / Matrix) renders and each link works from every page.

- [ ] **Step 9: Fix any visual or functional issues found**

If Step 8 surfaces a real problem, fix it in the smallest way that addresses it, re-verify in the browser, and re-run the full test suite (`cd idea_space && python -m pytest tests/ -v`) to confirm no regression.

- [ ] **Step 10: Stop the dev server and clean up**

Stop the background server process and delete the test database (`idea_space/idea_space.db`).

- [ ] **Step 11: Commit (only if Step 9 made changes)**

```bash
git add -A idea_space/
git commit -m "fix: address issues found in cross-app verification"
```

If no changes were needed, skip this step.

---

## Plan Self-Review Notes

- **Spec coverage:** Requirement/Stakeholder/Decision/Risk CRUD (Tasks 2-5) · many-to-many links to each other and to Task (Tasks 1, 6) · read-only traceability matrix (Task 7) · navigation bar (Task 8) — every spec section has a covering task.
- **Type consistency checked:** `_requirement_page_context(db, requirement) -> dict` (Task 5) is called identically in `edit_requirement` (Task 5) and all four `link_*` endpoints (Task 6) — same two positional arguments, same return shape consumed by `requirements/_page.html`. `_all_stakeholders`/`_all_decisions`/`_all_risks` naming and signatures are consistent within their own routers (Tasks 2-4) and don't need to be shared across files. `VALID_REQUIREMENT_STATUSES` (Task 5) and `VALID_SEVERITY_LIKELIHOOD`/`VALID_RISK_STATUSES` (Task 4) are each referenced only within their own router.
- **htmx-fragment safety checked:** every template rendered as an htmx response target (`stakeholders/_manager.html`, `decisions/_manager.html`, `risks/_manager.html`, `requirements/_list_only.html`, `requirements/_page.html`) has exactly one root element and is never also used as a `{% block content %}` body directly — `list.html` and `detail.html` each `{% include %}` the fragment rather than duplicating its markup, matching the Global Constraints rule.
- **No placeholders:** every step includes complete, runnable code; no "TBD"/"similar to Task N" shortcuts.
