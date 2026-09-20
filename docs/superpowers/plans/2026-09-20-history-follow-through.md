# Idea Space — Confidence, History & Follow-Through (Slice 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an activity/audit log, completion notes, task archiving, and a whole-app visual restyle using the SOL design system to the existing Idea Space Slice 1 codebase.

**Architecture:** A new `app/services/activity.py` module provides `record_change()`, called explicitly from the existing `complete_task` and `reschedule_task` endpoints and a new `archive_task` endpoint. A generic `ActivityLog` table stores all tracked changes. `Task` gains a nullable `completion_note` column and a third `"archived"` status value. The visual restyle is achieved almost entirely by writing `app/static/app.css` against class/id selectors that already exist in the current templates (`.task`, `#task-list`, `.filter-bar`, `.label-chip`, `#label-manager`, `#reminder-banner`, `.calendar-week`, `.calendar-day`, `button[type="submit"]`), plus one small branding addition to `base.html`.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0.54 (SQLite), Jinja2, htmx, pytest, httpx — same stack as Slice 1, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-20-history-follow-through-design.md`

## Global Constraints

- `record_change(db, task, field_name, old_value, new_value)` adds an `ActivityLog` row to the session but does **not** commit — callers commit alongside their own state change, matching this codebase's existing explicit-commit style.
- Only `"status"` and `"due_date"` are ever written as `field_name` values in this slice. No SQLAlchemy event hooks — logging calls are explicit, at the exact point each field changes.
- `Task.status` now allows `"open" | "done" | "archived"`. Archiving is manual, done-tasks-only, via `POST /tasks/{task_id}/archive` (404 for any other status).
- `completion_note` is nullable `Text` on `Task`; an empty submitted string normalizes to `None`. A recurring task's successor never inherits the parent's `completion_note`.
- `GET /tasks?status=...` returns `400` for any value outside `{"open", "done", "archived"}`.
- SOL design tokens live in `docs/superpowers/DESIGN.md`. The restyle is presentation-only — no behavioral changes to any existing flow.
- Every task must leave the full test suite (`cd idea_space && python -m pytest tests/ -v`) passing with pristine output before committing.

---

## File Structure

```
idea_space/
  app/
    models.py                          # MODIFY: add ActivityLog, Task.completion_note
    services/
      activity.py                      # CREATE: record_change()
    routers/
      tasks.py                         # MODIFY: complete_task, reschedule_task, list_tasks;
                                        #   add archive_task, task_history
    templates/
      base.html                        # MODIFY: add <header> branding
      tasks/
        _row.html                      # MODIFY: completion-note input, Archive button, History toggle
        _list_fragment.html            # MODIFY: add status nav (Open/Done/Archived)
        _history.html                  # CREATE: history fragment
    static/
      app.css                          # MODIFY: full SOL-token-based rebuild
  tests/
    test_activity.py                   # CREATE
    test_tasks.py                      # MODIFY: append new test cases
```

---

### Task 1: Data model — ActivityLog, Task.completion_note, record_change service

**Files:**
- Modify: `idea_space/app/models.py`
- Create: `idea_space/app/services/activity.py`
- Create: `idea_space/tests/test_activity.py`

**Interfaces:**
- Consumes: `app.db.Base`, `app.models.Task` (existing), `app.seed.seed_default_workspace` (existing).
- Produces: `app.models.ActivityLog` (fields: `id, workspace_id, task_id, field_name, old_value, new_value, changed_at`). `app.models.Task.completion_note: str | None`. `app.services.activity.record_change(db: Session, task: Task, field_name: str, old_value: str | None, new_value: str) -> None` — adds (does not commit) an `ActivityLog` row.

- [ ] **Step 1: Write the failing test**

`idea_space/tests/test_activity.py`:

```python
from datetime import datetime, timezone

from app.models import ActivityLog, Task
from app.seed import seed_default_workspace
from app.services.activity import record_change

UTC = timezone.utc


def test_task_has_completion_note_field_defaulting_to_none(db_session):
    workspace, user = seed_default_workspace(db_session)
    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Draft outline",
        due_date=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
    )
    db_session.add(task)
    db_session.commit()

    assert task.completion_note is None


def test_record_change_writes_activity_log_row(db_session):
    workspace, user = seed_default_workspace(db_session)
    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Draft outline",
        due_date=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    record_change(db_session, task, "status", "open", "done")
    db_session.commit()

    entries = db_session.query(ActivityLog).filter_by(task_id=task.id).all()
    assert len(entries) == 1
    assert entries[0].field_name == "status"
    assert entries[0].old_value == "open"
    assert entries[0].new_value == "done"
    assert entries[0].workspace_id == workspace.id


def test_record_change_allows_null_old_value(db_session):
    workspace, user = seed_default_workspace(db_session)
    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Draft outline",
        due_date=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    record_change(db_session, task, "due_date", None, "2026-09-22")
    db_session.commit()

    entry = db_session.query(ActivityLog).filter_by(task_id=task.id).one()
    assert entry.old_value is None
    assert entry.new_value == "2026-09-22"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_activity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.activity'` (and `ActivityLog` not defined).

- [ ] **Step 3: Add ActivityLog and completion_note to models.py**

Modify `idea_space/app/models.py` — add `completion_note` to the `Task` class (insert after `completed_at`):

```python
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completion_note: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Add a new `ActivityLog` class at the end of the file (after `Reminder`):

```python
class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    field_name: Mapped[str] = mapped_column(String(50))
    old_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_value: Mapped[str] = mapped_column(String(255))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

- [ ] **Step 4: Write app/services/activity.py**

```python
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import ActivityLog, Task


def record_change(
    db: Session,
    task: Task,
    field_name: str,
    old_value: str | None,
    new_value: str,
) -> None:
    entry = ActivityLog(
        workspace_id=task.workspace_id,
        task_id=task.id,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        changed_at=datetime.now(timezone.utc),
    )
    db.add(entry)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (48 tests: 45 existing + 3 new).

- [ ] **Step 6: Commit**

```bash
git add idea_space/app/models.py idea_space/app/services/activity.py idea_space/tests/test_activity.py
git commit -m "feat: add ActivityLog model, Task.completion_note, and record_change service"
```

---

### Task 2: Completion notes + status-change logging

**Files:**
- Modify: `idea_space/app/routers/tasks.py`
- Modify: `idea_space/tests/test_tasks.py`

**Interfaces:**
- Consumes: `app.services.activity.record_change` (Task 1), `app.models.ActivityLog` (Task 1).
- Produces: `POST /tasks/{task_id}/complete` now accepts an optional `completion_note` form field, stores it on the task, and writes an `ActivityLog` entry (`field_name="status"`, `old_value=<task's status before completion>`, `new_value="done"`).

- [ ] **Step 1: Write the failing test**

Append to `idea_space/tests/test_tasks.py`:

```python
def test_complete_task_with_note_stores_it(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()

    client.post(f"/tasks/{task.id}/complete", data={"completion_note": "Sent to stakeholders"})

    db_session.refresh(task)
    assert task.completion_note == "Sent to stakeholders"


def test_complete_task_without_note_leaves_it_none(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()

    client.post(f"/tasks/{task.id}/complete")

    db_session.refresh(task)
    assert task.completion_note is None


def test_complete_task_with_empty_note_normalizes_to_none(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()

    client.post(f"/tasks/{task.id}/complete", data={"completion_note": ""})

    db_session.refresh(task)
    assert task.completion_note is None


def test_complete_task_logs_status_change(client, db_session):
    from app.models import ActivityLog, Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()

    client.post(f"/tasks/{task.id}/complete")

    entry = db_session.query(ActivityLog).filter_by(task_id=task.id, field_name="status").one()
    assert entry.old_value == "open"
    assert entry.new_value == "done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_tasks.py -v`
Expected: FAIL — `completion_note` is not accepted/stored, and no `ActivityLog` row is created.

- [ ] **Step 3: Update complete_task**

Modify `idea_space/app/routers/tasks.py` — add the import (alongside the existing imports at the top):

```python
from app.services.activity import record_change
```

Replace the `complete_task` function:

```python
@router.post("/tasks/{task_id}/complete")
def complete_task(
    request: Request,
    task_id: int,
    completion_note: str | None = Form(None),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    record_change(db, task, "status", task.status, "done")
    task.status = "done"
    task.completed_at = datetime.now(timezone.utc)
    task.completion_note = completion_note or None
    db.commit()

    if task.recurrence_active:
        # SQLite strips tzinfo on read-back; normalize before using in compute_next_due_date
        if task.due_date.tzinfo is None:
            task.due_date = task.due_date.replace(tzinfo=timezone.utc)

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
                labels=list(task.labels),
            )
            db.add(successor)
            db.commit()

    tasks = _open_tasks(db)
    all_labels = db.query(Label).order_by(Label.name.asc()).all()
    return templates.TemplateResponse(
        request,
        "tasks/_task_list_only.html",
        {"tasks": tasks, "all_labels": all_labels},
    )
```

(Only the function signature, the `record_change(...)` call, and the `task.completion_note = ...` line are new — the recurrence-spawn body and the trailing response are unchanged from the current file.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (52 tests).

- [ ] **Step 5: Commit**

```bash
git add idea_space/app/routers/tasks.py idea_space/tests/test_tasks.py
git commit -m "feat: add optional completion notes and log status changes on complete"
```

---

### Task 3: Reschedule due-date logging

**Files:**
- Modify: `idea_space/app/routers/tasks.py`
- Modify: `idea_space/tests/test_tasks.py`

**Interfaces:**
- Consumes: `app.services.activity.record_change` (Task 1).
- Produces: `PATCH /tasks/{task_id}/reschedule` now writes an `ActivityLog` entry (`field_name="due_date"`, `old_value=<"YYYY-MM-DD" before>`, `new_value=<"YYYY-MM-DD" after>`) before applying the date change.

- [ ] **Step 1: Write the failing test**

Append to `idea_space/tests/test_tasks.py`:

```python
def test_reschedule_logs_due_date_change(client, db_session):
    from app.models import ActivityLog, Task

    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    client.post(
        "/tasks",
        data={"title": "Stakeholder sync", "due_date": due.strftime("%Y-%m-%dT%H:%M")},
    )
    task = db_session.query(Task).filter_by(title="Stakeholder sync").one()

    client.patch(f"/tasks/{task.id}/reschedule", data={"due_date": "2026-09-24"})

    entry = db_session.query(ActivityLog).filter_by(task_id=task.id, field_name="due_date").one()
    assert entry.old_value == "2026-09-22"
    assert entry.new_value == "2026-09-24"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_tasks.py -v`
Expected: FAIL — no `ActivityLog` row with `field_name="due_date"` exists.

- [ ] **Step 3: Update reschedule_task**

Modify `idea_space/app/routers/tasks.py` — replace the `reschedule_task` function body:

```python
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

    old_date_str = task.due_date.strftime("%Y-%m-%d")
    new_date = datetime.strptime(due_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    task.due_date = task.due_date.replace(
        year=new_date.year, month=new_date.month, day=new_date.day
    )
    record_change(db, task, "due_date", old_date_str, due_date)
    db.commit()

    return calendar_router.calendar_week(request, start=None, db=db)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (53 tests).

- [ ] **Step 5: Commit**

```bash
git add idea_space/app/routers/tasks.py idea_space/tests/test_tasks.py
git commit -m "feat: log due-date changes on reschedule"
```

---

### Task 4: Archiving + status validation + status nav

**Files:**
- Modify: `idea_space/app/routers/tasks.py`
- Modify: `idea_space/app/templates/tasks/_row.html`
- Modify: `idea_space/app/templates/tasks/_list_fragment.html`
- Modify: `idea_space/tests/test_tasks.py`

**Interfaces:**
- Consumes: `_filtered_tasks`, `record_change` (existing/Task 1).
- Produces: `POST /tasks/{task_id}/archive` — 404 unless the task exists and `status == "done"`; sets `status = "archived"`, logs the status change, returns the re-filtered `"done"` list (the archived task disappears from it). `GET /tasks?status=<anything other than open|done|archived>` now returns `400`.

- [ ] **Step 1: Write the failing test**

Append to `idea_space/tests/test_tasks.py`:

```python
def test_archive_requires_done_status(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()

    response = client.post(f"/tasks/{task.id}/archive")
    assert response.status_code == 404


def test_archive_moves_task_from_done_to_archived_view(client, db_session):
    from app.models import ActivityLog, Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()
    client.post(f"/tasks/{task.id}/complete")

    response = client.post(f"/tasks/{task.id}/archive")
    assert response.status_code == 200
    assert b"Draft outline" not in response.content

    db_session.refresh(task)
    assert task.status == "archived"

    entry = (
        db_session.query(ActivityLog)
        .filter_by(task_id=task.id, field_name="status", new_value="archived")
        .one()
    )
    assert entry.old_value == "done"

    done_view = client.get("/tasks?status=done")
    assert b"Draft outline" not in done_view.content

    archived_view = client.get("/tasks?status=archived")
    assert b"Draft outline" in archived_view.content


def test_list_tasks_rejects_invalid_status(client):
    response = client.get("/tasks?status=banana")
    assert response.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_tasks.py -v`
Expected: FAIL — `POST /tasks/{id}/archive` doesn't exist (404 from routing, not from the intended check), and `?status=banana` currently returns `200` with an empty list instead of `400`.

- [ ] **Step 3: Add status validation to list_tasks and add archive_task**

Modify `idea_space/app/routers/tasks.py` — add a module-level constant near the top (after the `templates = ...` line):

```python
VALID_STATUSES = {"open", "done", "archived"}
```

Modify `list_tasks` to validate `status` (insert as the first line of the function body):

```python
@router.get("/tasks")
def list_tasks(
    request: Request,
    labels: str | None = None,
    status: str = "open",
    db: Session = Depends(get_db),
):
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

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

Add `archive_task` after `complete_task`:

```python
@router.post("/tasks/{task_id}/archive")
def archive_task(request: Request, task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None or task.status != "done":
        raise HTTPException(status_code=404, detail="Task not found or not done")

    record_change(db, task, "status", "done", "archived")
    task.status = "archived"
    db.commit()

    tasks = _filtered_tasks(db, None, "done")
    all_labels = db.query(Label).order_by(Label.name.asc()).all()
    return templates.TemplateResponse(
        request,
        "tasks/_task_list_only.html",
        {"tasks": tasks, "all_labels": all_labels},
    )
```

- [ ] **Step 4: Add the Archive button to _row.html**

Modify `idea_space/app/templates/tasks/_row.html` — add after the "Done" button line:

```html
  <button hx-post="/tasks/{{ task.id }}/complete" hx-target="#task-list" hx-swap="outerHTML">Done</button>
  {% if task.status == "done" %}
  <button hx-post="/tasks/{{ task.id }}/archive" hx-target="#task-list" hx-swap="outerHTML">Archive</button>
  {% endif %}
</li>
```

(This replaces the file's final two lines — the "Done" button line and the closing `</li>` — with the three lines above.)

- [ ] **Step 5: Add the status nav to _list_fragment.html**

Modify `idea_space/app/templates/tasks/_list_fragment.html`:

```html
{% include "tasks/_form.html" %}
{% include "labels/_filter_bar.html" %}
<nav class="status-nav">
  <a href="/tasks?status=open">Open</a>
  <a href="/tasks?status=done">Done</a>
  <a href="/tasks?status=archived">Archived</a>
</nav>
<nav class="filter-bar">
  {% for label in all_labels|default([]) %}
  <a href="/tasks?labels={{ label.id }}{% if status|default('open') != 'open' %}&status={{ status }}{% endif %}"
     class="label-chip{% if label.id in selected_label_ids|default([]) %} label-chip--active{% endif %}"
     style="background-color: {{ label.color }};">{{ label.name }}</a>
  {% endfor %}
  <a href="/tasks">Clear filters</a>
</nav>
{% include "tasks/_task_list_only.html" %}
```

(Only the new `<nav class="status-nav">` block is added; everything else in the file is unchanged.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (56 tests).

- [ ] **Step 7: Commit**

```bash
git add idea_space/app/routers/tasks.py idea_space/app/templates/tasks/_row.html idea_space/app/templates/tasks/_list_fragment.html idea_space/tests/test_tasks.py
git commit -m "feat: add task archiving, status validation, and an Open/Done/Archived nav"
```

---

### Task 5: Activity history view

**Files:**
- Modify: `idea_space/app/routers/tasks.py`
- Create: `idea_space/app/templates/tasks/_history.html`
- Modify: `idea_space/app/templates/tasks/_row.html`
- Modify: `idea_space/tests/test_tasks.py`

**Interfaces:**
- Consumes: `app.models.ActivityLog` (Task 1).
- Produces: `GET /tasks/{task_id}/history` — 404 for an unknown task id; otherwise renders `tasks/_history.html` with that task's `ActivityLog` entries (newest first) and its `completion_note`.

- [ ] **Step 1: Write the failing test**

Append to `idea_space/tests/test_tasks.py`:

```python
def test_history_lists_entries_newest_first_and_includes_note(client, db_session):
    from app.models import Task

    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    client.post(
        "/tasks",
        data={"title": "Stakeholder sync", "due_date": due.strftime("%Y-%m-%dT%H:%M")},
    )
    task = db_session.query(Task).filter_by(title="Stakeholder sync").one()

    client.patch(f"/tasks/{task.id}/reschedule", data={"due_date": "2026-09-24"})
    client.post(f"/tasks/{task.id}/complete", data={"completion_note": "Done early"})

    response = client.get(f"/tasks/{task.id}/history")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Done early" in body
    assert "due_date" in body
    assert "status" in body
    assert body.index("status") < body.index("due_date")


def test_history_unknown_task_returns_404(client):
    response = client.get("/tasks/999/history")
    assert response.status_code == 404


def test_history_empty_for_task_with_no_changes(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()

    response = client.get(f"/tasks/{task.id}/history")
    assert response.status_code == 200
    assert b"No changes recorded yet" in response.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_tasks.py -v`
Expected: FAIL with `404 Not Found` for `GET /tasks/{id}/history` (route doesn't exist).

- [ ] **Step 3: Add the history endpoint**

Modify `idea_space/app/routers/tasks.py` — add the import (alongside existing imports):

```python
from app.models import ActivityLog, Label, Task
```

(This replaces the existing `from app.models import Label, Task` import line.)

Add `task_history` after `archive_task`:

```python
@router.get("/tasks/{task_id}/history")
def task_history(request: Request, task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    entries = (
        db.query(ActivityLog)
        .filter(ActivityLog.task_id == task_id)
        .order_by(ActivityLog.changed_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "tasks/_history.html",
        {"task_id": task_id, "entries": entries, "completion_note": task.completion_note},
    )
```

- [ ] **Step 4: Write templates/tasks/_history.html**

```html
<div id="history-{{ task_id }}" class="task-history">
  {% if completion_note %}
  <p class="history-note"><strong>Note:</strong> {{ completion_note }}</p>
  {% endif %}
  {% if not entries %}
  <p class="history-empty">No changes recorded yet.</p>
  {% else %}
  <ul class="history-list">
    {% for entry in entries %}
    <li>{{ entry.changed_at.strftime('%Y-%m-%d %H:%M') }} — {{ entry.field_name }}: {{ entry.old_value }} → {{ entry.new_value }}</li>
    {% endfor %}
  </ul>
  {% endif %}
</div>
```

- [ ] **Step 5: Add the History toggle to _row.html**

Modify `idea_space/app/templates/tasks/_row.html` — add the toggle button and an empty placeholder div right before the closing `</li>` (after the Archive button block from Task 4):

```html
  {% if task.status == "done" %}
  <button hx-post="/tasks/{{ task.id }}/archive" hx-target="#task-list" hx-swap="outerHTML">Archive</button>
  {% endif %}
  <button hx-get="/tasks/{{ task.id }}/history" hx-target="#history-{{ task.id }}" hx-swap="innerHTML">History</button>
  <div id="history-{{ task.id }}" class="task-history"></div>
</li>
```

(After Task 4, the file's final four lines are the Archive `{% if %}`/button/`{% endif %}` block and the closing `</li>`. This step keeps that block as-is and inserts the History button and placeholder div between `{% endif %}` and `</li>`, per the six lines shown above.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (59 tests).

- [ ] **Step 7: Commit**

```bash
git add idea_space/app/routers/tasks.py idea_space/app/templates/tasks/_history.html idea_space/app/templates/tasks/_row.html idea_space/tests/test_tasks.py
git commit -m "feat: add per-task activity history view"
```

---

### Task 6: SOL design system — app.css rebuild + branding header

**Files:**
- Modify: `idea_space/app/static/app.css`
- Modify: `idea_space/app/templates/base.html`
- Modify: `idea_space/tests/test_health.py`

**Interfaces:**
- Consumes: color/typography/spacing/radius tokens from `docs/superpowers/DESIGN.md`. Styles the class/id vocabulary already present in existing templates (`.task`, `.task--overdue`, `.task--virtual`, `.task-title`, `.task-due`, `.task-recurring`, `#task-list`, `.filter-bar`, `.status-nav`, `.label-chip`, `.label-chip--active`, `#label-manager`, `.label-manager-list`, `#reminder-banner`, `.reminder`, `.calendar-week`, `.calendar-day`, `.calendar-overdue`, `.task-history`, `.history-note`, `.history-list`, `button[type="submit"]`) — no template class-name changes are needed for the restyle itself, since this vocabulary already exists across the templates from Slices 1–2.
- Produces: `GET /static/app.css` returns `200` with CSS content (verified by a smoke test).

- [ ] **Step 1: Write the failing test**

Append to `idea_space/tests/test_health.py`:

```python
def test_static_css_is_served():
    response = client.get("/static/app.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd idea_space && python -m pytest tests/test_health.py -v`
Expected: PASS already (the file exists from Slice 1 with one rule in it) — this step just confirms the smoke test itself works; the real change in this task is content, not existence. Run it now to see it pass on the *current* (pre-rebuild) file, establishing your baseline before the rewrite.

- [ ] **Step 3: Rebuild app.css**

Replace the full contents of `idea_space/app/static/app.css`:

```css
:root {
  --color-surface-paper: #fcfbf8;
  --color-surface-white: #ffffff;
  --color-surface-container-low: #f4f2ff;
  --color-surface-blue-tint: #ecEEFC;
  --color-surface-green-tint: #eaf6eb;
  --color-line: #e2e4e9;
  --color-outline-variant: #c5c5d8;
  --color-ink-900: #16213e;
  --color-ink-500: #5a6276;
  --color-ink-300: #9097a6;
  --color-primary: #001ac3;
  --color-primary-container: #2a3cdc;
  --color-on-primary: #ffffff;
  --color-accent-red: #d6482e;
  --color-error-container: #ffdad6;

  --font-family: Arial, Helvetica, sans-serif;
  --font-size-h2: 18px;
  --font-size-body: 13px;
  --font-size-caption: 11.5px;
  --font-size-label: 12.5px;

  --radius-sm: 0.125rem;
  --radius-md: 0.375rem;
  --radius-full: 9999px;

  --space-xs: 0.25rem;
  --space-sm: 0.5rem;
  --space-md: 1rem;
  --space-lg: 1.5rem;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: var(--font-family);
  font-size: var(--font-size-body);
  line-height: 1.45;
  color: var(--color-ink-900);
  background: var(--color-surface-paper);
}

main {
  max-width: 900px;
  margin: 0 auto;
  padding: var(--space-lg) var(--space-md);
}

.app-header {
  background: var(--color-surface-white);
  border-bottom: 1px solid var(--color-line);
  padding: var(--space-md);
}

.app-header h1 {
  max-width: 900px;
  margin: 0 auto;
  font-size: var(--font-size-h2);
  font-weight: 700;
  color: var(--color-primary);
}

h2, h3 {
  font-family: var(--font-family);
  font-weight: 700;
  line-height: 1.2;
  margin: 0 0 var(--space-md) 0;
  color: var(--color-ink-900);
}

h3 {
  font-size: var(--font-size-label);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-ink-500);
}

input, select, textarea, button {
  font-family: var(--font-family);
  font-size: var(--font-size-body);
}

input[type="text"], input[type="number"], input[type="datetime-local"],
input[type="date"], input[type="color"], select, textarea {
  border: 1px solid var(--color-outline-variant);
  border-radius: var(--radius-sm);
  padding: var(--space-xs) var(--space-sm);
  color: var(--color-ink-900);
  background: var(--color-surface-white);
}

textarea {
  resize: vertical;
}

button {
  font-weight: 700;
  border: 1px solid var(--color-outline-variant);
  border-radius: var(--radius-sm);
  padding: var(--space-xs) var(--space-md);
  background: var(--color-surface-white);
  color: var(--color-ink-900);
  cursor: pointer;
}

button:hover {
  background: var(--color-surface-container-low);
}

button[type="submit"] {
  background: var(--color-primary-container);
  color: var(--color-on-primary);
  border-color: var(--color-primary-container);
}

button[type="submit"]:hover {
  opacity: 0.9;
}

form {
  display: inline-flex;
  gap: var(--space-xs);
  align-items: center;
  margin: 0 var(--space-xs) var(--space-xs) 0;
}

.filter-bar, .status-nav {
  display: flex;
  gap: var(--space-sm);
  align-items: center;
  margin: var(--space-md) 0;
  padding-bottom: var(--space-sm);
  border-bottom: 1px solid var(--color-line);
}

.status-nav a, .filter-bar a {
  font-size: var(--font-size-label);
  font-weight: 700;
  color: var(--color-ink-500);
  text-decoration: none;
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-sm);
}

.status-nav a:hover, .filter-bar a:hover {
  background: var(--color-surface-blue-tint);
  color: var(--color-primary);
}

#task-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.task {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-xs);
  background: var(--color-surface-white);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
}

.task--overdue {
  border-color: var(--color-accent-red);
  background: var(--color-error-container);
}

.task--virtual {
  opacity: 0.55;
  font-style: italic;
}

.task-title {
  font-weight: 700;
}

.task-due {
  font-size: var(--font-size-caption);
  color: var(--color-ink-500);
}

.task-recurring {
  color: var(--color-primary);
}

.label-chip {
  display: inline-block;
  padding: 2px var(--space-sm);
  border-radius: var(--radius-full);
  font-size: var(--font-size-caption);
  font-weight: 700;
  color: #fff;
  text-decoration: none;
}

.label-chip--active {
  outline: 2px solid var(--color-ink-900);
}

.calendar-week {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: var(--space-sm);
}

.calendar-day {
  background: var(--color-surface-white);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  padding: var(--space-sm);
  min-height: 120px;
}

.calendar-day ul {
  list-style: none;
  padding: 0;
  margin: var(--space-xs) 0 0 0;
}

.calendar-overdue {
  margin-bottom: var(--space-md);
}

#reminder-banner {
  background: var(--color-surface-green-tint);
  border-bottom: 1px solid var(--color-line);
  padding: var(--space-sm) var(--space-md);
}

.reminder {
  display: flex;
  gap: var(--space-sm);
  align-items: center;
  margin-bottom: var(--space-xs);
}

#label-manager {
  background: var(--color-surface-white);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  margin-bottom: var(--space-md);
}

.label-manager-list {
  list-style: none;
  padding: 0;
  margin: var(--space-sm) 0 0 0;
}

.label-manager-list li {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xs) 0;
  border-bottom: 1px solid var(--color-line);
}

.task-history {
  flex-basis: 100%;
  font-size: var(--font-size-caption);
  color: var(--color-ink-500);
  border-top: 1px solid var(--color-line);
  margin-top: var(--space-xs);
  padding-top: var(--space-xs);
}

.history-note {
  color: var(--color-ink-900);
}

.history-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
```

- [ ] **Step 4: Add the branding header to base.html**

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
  <header class="app-header"><h1>Idea Space</h1></header>
  <div hx-get="/reminders/due" hx-trigger="load" hx-swap="outerHTML" id="reminder-banner"></div>
  <main>{% block content %}{% endblock %}</main>
  <script src="/static/app.js"></script>
</body>
</html>
```

(Only the new `<header>` line is added.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd idea_space && python -m pytest tests/ -v`
Expected: all PASS (60 tests).

- [ ] **Step 6: Commit**

```bash
git add idea_space/app/static/app.css idea_space/app/templates/base.html idea_space/tests/test_health.py
git commit -m "style: rebuild app.css from the SOL design system and add app branding header"
```

---

### Task 7: Manual cross-app visual verification

**Files:** none expected — this task verifies Task 6's restyle renders correctly across every view. If a visual bug is found, fix it in the smallest way that addresses it (a missing selector, a layout tweak) and note the fix in the commit.

**Interfaces:** none — this is a verification task, not a feature task.

- [ ] **Step 1: Start the dev server against a fresh database**

Run: `cd idea_space && rm -f idea_space.db && python -m uvicorn app.main:app --port 8420` (run in the background; leave it running for the remaining steps).

- [ ] **Step 2: Seed representative data**

```bash
curl -s -X POST http://127.0.0.1:8420/tasks -d "title=Draft+outline" -d "due_date=2026-09-22T10:00" > /dev/null
curl -s -X POST http://127.0.0.1:8420/tasks -d "title=Weekly+status+update" -d "due_date=2026-09-20T09:00" -d "recurrence_pattern=weekly" -d "recurrence_interval=1" > /dev/null
curl -s -X POST http://127.0.0.1:8420/labels -d "name=Urgent" -d "color=%23ef4444" > /dev/null
```

- [ ] **Step 3: Visually verify each view in a browser**

Navigate to and screenshot each of: `http://127.0.0.1:8420/tasks`, `http://127.0.0.1:8420/tasks?status=done` (complete a task first via the UI to populate this), `http://127.0.0.1:8420/tasks?status=archived` (archive that same task first via the UI), `http://127.0.0.1:8420/calendar`. For each, confirm: the branding header renders, task rows show as bordered cards with visible title/due-date/label-chip styling, the status nav and filter bar render as a styled row of links, the calendar renders as a 7-column grid with bordered day cells, no unstyled raw-HTML appearance remains, and no layout is broken (overlapping text, unreadable contrast).

- [ ] **Step 4: Verify the completion-note field, Archive button, and History view**

On an open task in `/tasks`, complete it with a note typed into the inline field next to Done; confirm it moves to the Done view. On that Done task, click Archive; confirm it moves to the Archived view and no longer appears in Done. Click "History" on the archived task; confirm the note and at least one status-change entry render correctly styled (not raw unstyled text dumped on the page).

- [ ] **Step 5: Fix any visual issues found**

If Step 3 or 4 surfaces a real rendering problem (not a pre-existing Slice 1 behavior unrelated to styling), fix it directly in `app.css` or the specific template, re-verify in the browser, and re-run the full test suite (`cd idea_space && python -m pytest tests/ -v`) to confirm no regression.

- [ ] **Step 6: Stop the dev server and clean up**

Stop the background server process and delete the test database (`idea_space/idea_space.db`) so it doesn't get committed.

- [ ] **Step 7: Commit (only if Step 5 made changes)**

```bash
git add idea_space/app/static/app.css idea_space/app/templates
git commit -m "style: fix visual issues found in cross-app verification"
```

If no changes were needed, skip this step — there is nothing to commit.

---

## Plan Self-Review Notes

- **Spec coverage:** Activity history (Tasks 1, 3, 5) · Completion notes (Tasks 1, 2) · Archiving (Task 4) · Status validation and nav (Task 4) · SOL design system restyle (Tasks 6, 7) — every spec section has a covering task.
- **Type consistency checked:** `record_change`'s signature (Task 1) matches its three call sites in Tasks 2, 3, and 4. `ActivityLog`'s field names (`field_name`, `old_value`, `new_value`, `changed_at`) are used consistently in the history endpoint (Task 5) and its template. `VALID_STATUSES` (Task 4) is referenced only in `list_tasks`; `archive_task` doesn't need it since it checks `task.status != "done"` directly.
- **No placeholders:** every step includes complete, runnable code; no "TBD"/"similar to Task N" shortcuts.
- **Design decision recorded:** the spec's stated archive-response mechanism ("hidden status/labels fields mirroring the currently-viewed filter") was simplified in Task 4 to always re-render the `"done"` filtered view after archiving, matching the existing (imperfect but consistent) convention already used by `complete_task`/`set_recurrence_active`, which always reset to the open view regardless of the filter the user was viewing. This is a plan-level refinement of the spec's mechanism, not a scope change — the goal ("archived task disappears from the done view") is met exactly.
