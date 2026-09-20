# Idea Space — Product Ops Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Idea Space's UI around the supplied "Product Ops" dark theme mockup — sidebar/topbar shell, Tasks NOW/NEXT/DONE board, Calendar month/week/agenda views, a Requirements dashboard with CSV export, and a Traceability matrix with computed coverage/status — without adding any new business entity.

**Architecture:** One shared design-token/layout overhaul (Task 2) underpins four independently-testable page rebuilds (Tasks 4-7), each reusing a shared computed-status helper (Task 3) where relevant, sitting on top of a small schema migration (Task 1).

**Tech Stack:** FastAPI, Jinja2, htmx 2.0.2, SQLite/SQLAlchemy 2.0.54, pytest, httpx TestClient — unchanged from the existing app.

**Spec:** `docs/superpowers/specs/2026-09-20-product-ops-redesign-design.md`

## Global Constraints

- Every htmx-targeted template MUST be single-root (exactly one top-level
  element) — never a multi-sibling fragment or a full page extending
  `base.html`. This is the app's standing lesson from Slice 1/2; apply it
  proactively to every new fragment in this plan.
- SQLite strips tzinfo on datetime read-back — any Python-level datetime
  comparison on a freshly-fetched model needs
  `if x.tzinfo is None: x = x.replace(tzinfo=timezone.utc)`, written back
  onto the actual attribute.
- New columns on existing tables need the hand-rolled idempotent
  `PRAGMA table_info` + `ALTER TABLE` migration pattern already used by
  `ensure_completion_note_column` in `app/main.py` — this codebase has no
  Alembic.
- No new "Test"/verification entity — the matrix's 4th column stays
  **Stakeholders**, not Tests (spec Non-Goals).
- No real search backend — the topbar search box is decorative markup only.
- No multi-user owner picker — only one seeded user exists until Slice 4;
  show it as a fixed, disabled selection.
- The mockup's inline lucide SVG icons are **not** reproduced pixel-for-
  pixel — the spec's Goals commit to color/typography/spacing fidelity,
  not icon artwork. Use small CSS shapes (dots, badges) and typography
  instead of inlining SVG icon paths; this keeps every task's template
  code focused on structure and correctness.
- Full test suite (`python -m pytest -q` from `idea_space/`) must pass
  before every commit.

---

### Task 1: Schema migration — `Task.blocked` and `Requirement.updated_at`

**Files:**
- Modify: `idea_space/app/models.py`
- Modify: `idea_space/app/main.py`
- Test: `idea_space/tests/test_health.py`

**Interfaces:**
- Produces: `Task.blocked: bool` (default `False`); `Requirement.updated_at: datetime` (default `_utcnow()` at creation); `app/main.py::ensure_redesign_columns(target_engine) -> None`, called from `on_startup` alongside the existing `ensure_completion_note_column`.

- [ ] **Step 1: Write the failing migration test**

Append to `idea_space/tests/test_health.py`:

```python
def test_startup_adds_redesign_columns_to_existing_tables(tmp_path):
    # Same rationale as test_startup_adds_completion_note_column_to_existing_tasks_table:
    # exercise the migration function directly against a raw-DDL legacy
    # database rather than reloading app modules mid-suite.
    from sqlalchemy import create_engine, text as sa_text

    from app.main import ensure_redesign_columns

    db_path = tmp_path / "pre_redesign.db"
    old_engine = create_engine(f"sqlite:///{db_path}")
    with old_engine.connect() as conn:
        conn.execute(sa_text(
            "CREATE TABLE tasks (id INTEGER PRIMARY KEY, workspace_id INTEGER, "
            "owner_id INTEGER, title TEXT, description TEXT, status TEXT, "
            "due_date DATETIME, recurrence_series_id INTEGER, recurrence_pattern TEXT, "
            "recurrence_interval INTEGER, recurrence_days_of_week TEXT, "
            "recurrence_active BOOLEAN, created_at DATETIME, completed_at DATETIME, "
            "completion_note TEXT)"
        ))
        conn.execute(sa_text(
            "CREATE TABLE requirements (id INTEGER PRIMARY KEY, workspace_id INTEGER, "
            "owner_id INTEGER, title TEXT, description TEXT, business_need TEXT, "
            "acceptance_criteria TEXT, status TEXT, created_at DATETIME)"
        ))
        conn.execute(sa_text(
            "INSERT INTO requirements (id, workspace_id, owner_id, title, description, "
            "business_need, acceptance_criteria, status, created_at) VALUES "
            "(1, 1, 1, 'Legacy req', '', '', '', 'draft', '2026-01-01 00:00:00')"
        ))
        conn.commit()

    ensure_redesign_columns(old_engine)

    with old_engine.connect() as conn:
        task_columns = {row[1] for row in conn.execute(sa_text("PRAGMA table_info(tasks)"))}
        assert "blocked" in task_columns

        requirement_columns = {
            row[1] for row in conn.execute(sa_text("PRAGMA table_info(requirements)"))
        }
        assert "updated_at" in requirement_columns

        backfilled = conn.execute(
            sa_text("SELECT updated_at FROM requirements WHERE id = 1")
        ).scalar()
        assert backfilled == "2026-01-01 00:00:00"

    # Idempotent: running again against an already-migrated db is a no-op.
    ensure_redesign_columns(old_engine)

    old_engine.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_health.py::test_startup_adds_redesign_columns_to_existing_tables -v`
Expected: FAIL with `ImportError: cannot import name 'ensure_redesign_columns'`

- [ ] **Step 3: Add the columns to the models**

In `idea_space/app/models.py`, in `class Task`, add after `completion_note`:

```python
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
```

In `class Requirement`, add after `created_at`:

```python
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

- [ ] **Step 4: Add the migration function and wire it into startup**

In `idea_space/app/main.py`, add after `ensure_completion_note_column`:

```python
def ensure_redesign_columns(target_engine) -> None:
    """Idempotently add tasks.blocked and requirements.updated_at to a
    pre-existing (pre-redesign) database.

    Same rationale as ensure_completion_note_column: create_all never adds
    columns to a table that already exists, so a database created before
    this redesign needs these two columns patched in directly.
    """
    with target_engine.connect() as conn:
        task_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(tasks)"))}
        if "blocked" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN blocked BOOLEAN DEFAULT 0"))
            conn.commit()

        requirement_columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(requirements)"))
        }
        if "updated_at" not in requirement_columns:
            conn.execute(text("ALTER TABLE requirements ADD COLUMN updated_at DATETIME"))
            conn.execute(
                text("UPDATE requirements SET updated_at = created_at WHERE updated_at IS NULL")
            )
            conn.commit()
```

Update `on_startup`:

```python
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    ensure_completion_note_column(engine)
    ensure_redesign_columns(engine)
    db = SessionLocal()
    try:
        seed_default_workspace(db)
    finally:
        db.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_health.py -v`
Expected: PASS (all tests in the file, including the new one)

- [ ] **Step 6: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: all existing tests still pass (106 passed before this task)

```bash
git add app/models.py app/main.py tests/test_health.py
git commit -m "feat: add Task.blocked and Requirement.updated_at with migration"
```

---

### Task 2: Design tokens, sidebar/topbar shell, and core CSS

**Files:**
- Modify: `idea_space/app/templates/base.html`
- Modify: `idea_space/app/static/app.css`
- Modify: `idea_space/tests/test_navigation.py` (pre-existing, asserts on nav markup this task changes)
- Test: `idea_space/tests/test_layout.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `base.html` reads a context variable `active_nav` (one of `"tasks"|"calendar"|"requirements"|"matrix"`, missing/empty renders no nav item active) to highlight the sidebar nav and set the breadcrumb. Every full-page route added or touched in Tasks 4-7 MUST pass `active_nav` in its context. CSS class names defined here (`.app-shell`, `.app-sidebar`, `.primary-nav`, `.nav-item`, `.nav-item--active`, `.topbar`, `.breadcrumb`, `.btn`, `.btn-primary`, `.btn-outline`, `.metrics-row`, `.metric-card`, `.metric-label`, `.metric-value`, `.metric-note`, `.panel`, `.panel-toolbar`, `.filter-tabs`, `.filter-tab`, `.filter-tab--active`, `.status-badge` + 4 modifiers, `.page-header`, `.page-eyebrow`, `.page-title`, `.page-subtitle`) are the shared vocabulary Tasks 4-7 build on — do not rename them there.

- [ ] **Step 1: Write the failing structural test**

Create `idea_space/tests/test_layout.py` — this codebase's tests use the
`client`/`db_session` pytest fixtures defined in `tests/conftest.py` (a
fresh in-memory-SQLite-backed `TestClient` per test), never a module-level
`TestClient(app)` — every test function below takes `client` as a
parameter:

```python
def test_tasks_page_renders_sidebar_and_active_nav(client):
    response = client.get("/tasks")
    assert response.status_code == 200
    body = response.text
    assert 'class="app-shell"' in body
    assert 'class="app-sidebar"' in body
    assert "IDEA SPACE" in body
    assert 'nav-item nav-item--active' in body
    assert 'href="/tasks"' in body


def test_calendar_page_has_different_active_nav_than_tasks(client):
    tasks_body = client.get("/tasks").text
    calendar_body = client.get("/calendar").text
    # Each page's own nav link is the one marked active.
    tasks_active_idx = tasks_body.index('nav-item nav-item--active')
    assert 'href="/tasks"' in tasks_body[tasks_active_idx - 40 : tasks_active_idx + 40]
    calendar_active_idx = calendar_body.index('nav-item nav-item--active')
    assert 'href="/calendar"' in calendar_body[calendar_active_idx - 40 : calendar_active_idx + 40]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_layout.py -v`
Expected: FAIL — current `base.html` has no `app-shell`/`app-sidebar`/active-nav markup, and no router passes `active_nav` yet.

- [ ] **Step 3: Rewrite `base.html`**

Replace the full contents of `idea_space/app/templates/base.html` with:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Idea Space</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <script src="https://unpkg.com/htmx.org@2.0.2"></script>
  <link rel="stylesheet" href="/static/app.css">
</head>
<body>
{% set nav_labels = {'tasks': 'TASKS', 'calendar': 'CALENDAR', 'requirements': 'REQUIREMENTS', 'matrix': 'TRACEABILITY'} %}
{% set current_nav = active_nav|default('') %}
<div class="app-shell">
  <aside class="app-sidebar">
    <div class="brand">
      <div class="brand-mark">IS</div>
      <div class="brand-text">
        <div class="brand-name">IDEA SPACE</div>
        <div class="brand-caption">PRODUCT OPS</div>
      </div>
    </div>
    <nav class="primary-nav">
      <div class="nav-label">WORKSPACE</div>
      <a class="nav-item{% if current_nav == 'tasks' %} nav-item--active{% endif %}" href="/tasks">Tasks</a>
      <a class="nav-item{% if current_nav == 'calendar' %} nav-item--active{% endif %}" href="/calendar">Calendar</a>
      <a class="nav-item{% if current_nav == 'requirements' %} nav-item--active{% endif %}" href="/requirements">Requirements</a>
      <a class="nav-item{% if current_nav == 'matrix' %} nav-item--active{% endif %}" href="/matrix">Traceability</a>
    </nav>
    <div class="sidebar-spacer"></div>
    <div class="workspace-status">
      <div class="status-row">
        <span class="status-label">SYSTEM STATUS</span>
        <span class="status-dot"></span>
      </div>
      <div class="status-value">All systems focused</div>
    </div>
  </aside>
  <div class="app-body">
    <div class="topbar">
      <div class="breadcrumb">
        <span class="breadcrumb-workspace">WORKSPACE</span>
        <span class="breadcrumb-slash">/</span>
        <span class="breadcrumb-current">{{ nav_labels.get(current_nav, '') }}</span>
      </div>
      <div class="topbar-actions">
        <div class="search-box">
          <span class="search-hint">Search anything</span>
          <span class="search-shortcut">&#8984; K</span>
        </div>
        <div class="user-avatar">AR</div>
      </div>
    </div>
    <div hx-get="/reminders/due" hx-trigger="load" hx-swap="outerHTML" id="reminder-banner"></div>
    <main>{% block content %}{% endblock %}</main>
  </div>
</div>
<script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Rewrite `app.css`**

Replace the full contents of `idea_space/app/static/app.css` with:

```css
:root {
  --bg: #0A0A0A;
  --sidebar-bg: #0D0E12;
  --panel-bg: #111318;
  --panel-bg-alt: #17191F;
  --border: #292B33;
  --text-primary: #F7F7F8;
  --text-muted: #9A9AA3;
  --text-placeholder: #6F717B;
  --accent: #A855F7;
  --accent-bg: #24142F;
  --success: #33D69F;
  --success-bg: #123128;
  --warning: #F5B942;
  --warning-bg: #332812;
  --danger: #FF6B7A;
  --danger-bg: #35171D;
  --font: 'Inter', system-ui, sans-serif;
  --radius-sm: 2px;
  --radius-md: 4px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: var(--font);
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-primary);
  background: var(--bg);
}

h2, h3 { font-family: var(--font); margin: 0; color: var(--text-primary); }

h3 {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  margin-bottom: 10px;
}

a { color: inherit; }

input, select, textarea, button { font-family: var(--font); font-size: 13px; }

input[type="text"], input[type="number"], input[type="datetime-local"],
input[type="date"], input[type="color"], select, textarea {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  color: var(--text-primary);
  background: var(--panel-bg-alt);
}

textarea { resize: vertical; }

button, .btn {
  font-weight: 700;
  font-size: 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 14px;
  background: var(--panel-bg-alt);
  color: var(--text-primary);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

button:hover, .btn:hover { background: var(--border); }

button[type="submit"], .btn-primary {
  background: var(--accent);
  color: #FFFFFF;
  border-color: var(--accent);
}

button[type="submit"]:hover, .btn-primary:hover { opacity: 0.9; }

.btn-outline { background: transparent; }

form {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin: 0 6px 6px 0;
}

/* ---- App shell ---- */

.app-shell { display: flex; min-height: 100vh; }

.app-sidebar {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 28px;
  padding: 28px 20px;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
}

.brand { display: flex; gap: 12px; align-items: center; }

.brand-mark {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  color: #FFFFFF;
  font-weight: 800;
  font-size: 12px;
}

.brand-name { font-size: 14px; font-weight: 700; }
.brand-caption { font-size: 9px; font-weight: 600; color: var(--text-muted); }

.primary-nav { display: flex; flex-direction: column; gap: 6px; }

.nav-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.nav-item {
  height: 42px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  border-left: 2px solid transparent;
  color: var(--text-muted);
  font-size: 13px;
  text-decoration: none;
}

.nav-item--active {
  background: var(--accent-bg);
  border-left-color: var(--accent);
  color: var(--text-primary);
  font-weight: 600;
}

.nav-item:hover:not(.nav-item--active) { color: var(--text-primary); }

.sidebar-spacer { flex: 1; }

.workspace-status {
  padding: 14px;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-row { display: flex; justify-content: space-between; align-items: center; }
.status-label { font-size: 9px; font-weight: 600; color: var(--text-muted); }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); }
.status-value { font-size: 12px; font-weight: 500; }

.app-body { flex: 1; display: flex; flex-direction: column; min-width: 0; }

.topbar {
  height: 76px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 40px;
  border-bottom: 1px solid var(--border);
}

.breadcrumb { display: flex; gap: 8px; align-items: center; font-size: 11px; }
.breadcrumb-workspace { font-weight: 600; color: var(--text-muted); }
.breadcrumb-slash { color: #555760; }
.breadcrumb-current { font-weight: 600; }

.topbar-actions { display: flex; gap: 10px; align-items: center; }

.search-box {
  width: 220px;
  height: 38px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 12px;
  background: var(--panel-bg);
  border: 1px solid var(--border);
}

.search-hint { font-size: 12px; color: var(--text-muted); flex: 1; }
.search-shortcut {
  font-size: 9px;
  font-weight: 600;
  color: var(--text-muted);
  padding: 3px 6px;
  background: var(--panel-bg-alt);
}

.user-avatar {
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  color: #FFFFFF;
  font-weight: 700;
  font-size: 11px;
}

main { padding: 32px 40px; }

#reminder-banner {
  background: var(--warning-bg);
  border-bottom: 1px solid var(--border);
  padding: 8px 40px;
}

#reminder-banner:empty { display: none; }

.reminder { display: flex; gap: 8px; align-items: center; margin-bottom: 4px; }

/* ---- Page header / metrics (shared across Tasks/Requirements/Matrix) ---- */

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 26px;
}

.page-eyebrow { font-size: 10px; font-weight: 700; color: var(--accent); margin-bottom: 7px; }
.page-title { font-size: 30px; font-weight: 400; margin-bottom: 7px; }
.page-subtitle { font-size: 14px; color: var(--text-muted); }

.metrics-row {
  display: flex;
  gap: 1px;
  background: var(--border);
  margin-bottom: 26px;
}

.metric-card {
  flex: 1;
  padding: 15px 18px;
  background: var(--panel-bg);
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.metric-label { font-size: 9px; font-weight: 700; color: var(--text-muted); }
.metric-value-row { display: flex; justify-content: space-between; align-items: flex-end; }
.metric-value { font-size: 24px; }
.metric-note { font-size: 9px; font-weight: 600; }
.metric-note--accent { color: var(--accent); }
.metric-note--warning { color: var(--warning); }
.metric-note--success { color: var(--success); }
.metric-note--danger { color: var(--danger); }

.panel {
  background: var(--panel-bg);
  border: 1px solid var(--border);
  padding: 20px;
}

.panel-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 14px;
  height: 48px;
  border-bottom: 1px solid var(--border);
}

.filter-tabs, .status-nav { display: flex; gap: 8px; }

.filter-tab, .status-nav a {
  height: 30px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  font-size: 9px;
  font-weight: 700;
  color: var(--text-muted);
  background: var(--panel-bg);
  text-decoration: none;
}

.filter-tab--active, .status-nav a.status-nav--active {
  background: var(--accent-bg);
  color: var(--accent);
}

.status-badge {
  display: inline-flex;
  padding: 5px 7px;
  font-size: 8px;
  font-weight: 700;
  text-transform: uppercase;
}

.status-badge--success { background: var(--success-bg); color: var(--success); }
.status-badge--warning { background: var(--warning-bg); color: var(--warning); }
.status-badge--danger { background: var(--danger-bg); color: var(--danger); }
.status-badge--neutral { background: var(--panel-bg-alt); color: var(--text-muted); }

/* ---- Tasks: quick capture, board, cards ---- */

.quick-capture {
  height: 74px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  margin-bottom: 26px;
}

.quick-capture-icon {
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-bg);
  color: var(--accent);
  font-weight: 700;
}

.quick-capture-fields { flex: 1; display: flex; flex-direction: column; gap: 3px; }
.quick-capture-label { font-size: 9px; font-weight: 700; color: var(--text-muted); }
.quick-capture-input {
  border: none;
  background: transparent;
  padding: 0;
  font-size: 14px;
  color: var(--text-primary);
  width: 100%;
}
.quick-capture-input::placeholder { color: var(--text-primary); }
.quick-capture-meta { font-size: 9px; font-weight: 700; color: var(--text-muted); }

.board-columns { display: flex; gap: 16px; align-items: flex-start; }

.board-column { flex: 1; display: flex; flex-direction: column; gap: 12px; min-width: 0; }

.board-column-header { display: flex; justify-content: space-between; align-items: center; }
.board-column-label-group { display: flex; gap: 8px; align-items: center; }
.board-column-dot { width: 7px; height: 7px; border-radius: 50%; }
.board-column-dot--now { background: var(--accent); }
.board-column-dot--next { background: var(--warning); }
.board-column-dot--done { background: var(--success); }
.board-column-label { font-size: 10px; font-weight: 700; }
.board-column-count { font-size: 10px; font-weight: 600; color: var(--text-muted); }

.task-card {
  padding: 16px;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.task-card--done .task-card-title { color: var(--text-muted); }

.task-card-title-row { display: flex; gap: 10px; align-items: flex-start; }

.task-card-checkbox { flex-shrink: 0; width: 16px; height: 16px; margin-top: 1px; }

.task-card-title { font-size: 13px; font-weight: 500; flex: 1; }

.task-card-meta { display: flex; justify-content: space-between; align-items: center; }

.task-card-tag {
  padding: 4px 7px;
  background: var(--panel-bg-alt);
  font-size: 9px;
  font-weight: 600;
  color: var(--text-muted);
}

.task-card-due { font-size: 9px; font-weight: 600; color: var(--text-muted); }
.task-card-due--done { color: var(--success); }

.task-card-blocked-badge {
  padding: 4px 7px;
  background: var(--danger-bg);
  color: var(--danger);
  font-size: 9px;
  font-weight: 700;
}

.task-card-actions { display: flex; flex-wrap: wrap; gap: 6px; }

.archived-link { font-size: 11px; color: var(--text-muted); text-decoration: none; }

.task-history {
  flex-basis: 100%;
  font-size: 11px;
  color: var(--text-muted);
  border-top: 1px solid var(--border);
  margin-top: 4px;
  padding-top: 4px;
}
.task-history:empty { display: none; }
.history-note { color: var(--text-primary); }
.history-list { list-style: none; margin: 0; padding: 0; }

.label-chip {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 700;
  color: #fff;
  text-decoration: none;
}
.label-chip--active { outline: 2px solid var(--text-primary); }

#label-manager, #stakeholder-manager, #decision-manager, #risk-manager {
  background: var(--panel-bg);
  border: 1px solid var(--border);
  padding: 16px;
  margin-bottom: 16px;
}

.label-manager-list, .entity-manager-list, .history-list {
  list-style: none;
  padding: 0;
  margin: 8px 0 0 0;
}

.label-manager-list li, .entity-manager-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}

/* ---- Calendar ---- */

.calendar-view-toggle { display: flex; gap: 1px; background: var(--border); }

.calendar-view-btn {
  height: 36px;
  display: flex;
  align-items: center;
  padding: 0 13px;
  font-size: 9px;
  font-weight: 700;
  color: var(--text-muted);
  background: var(--panel-bg);
  text-decoration: none;
}

.calendar-view-btn--active { background: var(--accent); color: #fff; }

.calendar-layout { display: flex; gap: 18px; align-items: flex-start; }

.calendar-main {
  flex: 1;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  min-width: 0;
}

.calendar-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 16px;
  height: 54px;
  border-bottom: 1px solid var(--border);
}

.calendar-weekday-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  background: var(--border);
}

.calendar-weekday {
  padding: 8px 10px;
  background: var(--panel-bg-alt);
  font-size: 9px;
  font-weight: 700;
  color: var(--text-muted);
}

.calendar-month-grid, .calendar-week {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  background: var(--border);
}

.calendar-day {
  background: var(--panel-bg);
  padding: 10px;
  min-height: 100px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.calendar-day--today .calendar-day-number { color: var(--accent); font-weight: 700; }
.calendar-day--other-month { opacity: 0.4; }

.calendar-day-number { font-size: 11px; color: var(--text-muted); font-weight: 500; }

.calendar-day ul { list-style: none; padding: 0; margin: 0; }

.calendar-event { display: flex; gap: 6px; align-items: center; }
.calendar-event-marker { width: 3px; height: 18px; flex-shrink: 0; }
.calendar-event-name { font-size: 9px; font-weight: 500; }

.calendar-overdue { margin-bottom: 16px; padding: 0 16px; }

.calendar-agenda-list { list-style: none; padding: 16px; margin: 0; }

.calendar-agenda-item {
  display: flex;
  gap: 12px;
  padding: 11px 0;
  border-bottom: 1px solid var(--border);
}

.agenda-empty { padding: 16px; color: var(--text-muted); font-size: 12px; }

.upcoming-agenda {
  width: 290px;
  flex-shrink: 0;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

/* ---- Requirements ---- */

.requirements-layout { display: flex; gap: 18px; align-items: flex-start; }

.requirements-table { flex: 1; background: var(--panel-bg); border: 1px solid var(--border); }

#requirement-list { list-style: none; margin: 0; padding: 0; }

.requirement {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border-bottom: 1px solid var(--border);
}

.requirement-id { width: 58px; flex-shrink: 0; font-size: 10px; font-weight: 700; color: var(--accent); }
.requirement-main { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.requirement-title { font-size: 12px; font-weight: 500; text-decoration: none; color: var(--text-primary); }
.requirement-meta { font-size: 9px; color: var(--text-muted); }
.requirement-owner { width: 100px; flex-shrink: 0; font-size: 10px; color: var(--text-muted); }
.requirement-status { width: 92px; flex-shrink: 0; }
.requirement-links { width: 50px; flex-shrink: 0; font-size: 10px; font-weight: 700; color: var(--text-muted); }

.create-panel {
  width: 330px;
  flex-shrink: 0;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field-group { display: flex; flex-direction: column; gap: 7px; }
.field-label { font-size: 8px; font-weight: 700; color: var(--text-muted); }
.field-input {
  width: 100%;
  background: var(--panel-bg-alt);
  border: 1px solid var(--border);
  padding: 12px;
  color: var(--text-primary);
}

/* ---- Matrix ---- */

.matrix-layout { display: flex; gap: 18px; align-items: flex-start; }

.matrix-table { width: 100%; border-collapse: collapse; flex: 1; }

.matrix-table th, .matrix-table td {
  border: 1px solid var(--border);
  padding: 10px;
  text-align: left;
  font-size: 11px;
}

.matrix-table th {
  background: var(--panel-bg-alt);
  font-size: 8px;
  font-weight: 700;
  color: var(--text-muted);
}

.matrix-empty { color: var(--text-placeholder); }

.link-badge {
  width: 30px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  font-weight: 700;
}

.link-badge--linked { background: var(--success-bg); color: var(--success); }
.link-badge--partial { background: var(--warning-bg); color: var(--warning); }
.link-badge--missing { background: var(--danger-bg); color: var(--danger); }

.matrix-legend { display: flex; gap: 14px; align-items: center; }
.legend-item { display: flex; gap: 6px; align-items: center; font-size: 8px; font-weight: 700; color: var(--text-muted); }
.legend-dot { width: 6px; height: 6px; border-radius: 50%; }

.coverage-panel {
  width: 290px;
  flex-shrink: 0;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.coverage-ring-area {
  height: 170px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  justify-content: center;
  background: var(--panel-bg-alt);
}

.coverage-ring {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  background: conic-gradient(var(--accent) calc(var(--pct) * 1%), var(--panel-bg) 0);
}

.coverage-ring-value { font-size: 10px; font-weight: 700; }

.attention-item {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 11px 0;
  border-bottom: 1px solid var(--border);
}

.attention-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.attention-detail { display: flex; flex-direction: column; gap: 3px; }
.attention-id { font-size: 9px; font-weight: 700; }
.attention-text { font-size: 10px; font-weight: 500; }
```

- [ ] **Step 5: Wire `active_nav` into the existing 4 full-page routes**

These 4 templates are the only ones extending `base.html` today; pass
`active_nav` from each router so Step 1's test passes for `/tasks` and
`/calendar` (the requirements/matrix wiring lands fully in Tasks 6-7, but
add it here too since it's a one-line addition to an existing dict):

In `idea_space/app/routers/tasks.py`, in `list_tasks`, add `"active_nav": "tasks"` to the returned context dict.

In `idea_space/app/routers/calendar.py`, in `calendar_week`, add `"active_nav": "calendar"` to the returned context dict.

In `idea_space/app/routers/requirements.py`, in `list_requirements` and `requirement_detail`, add `"active_nav": "requirements"` to each returned context dict.

In `idea_space/app/routers/matrix.py`, in `traceability_matrix`, add `"active_nav": "matrix"` to the returned context dict.

- [ ] **Step 6: Update the pre-existing nav test**

`idea_space/tests/test_navigation.py` asserts on the old header's
`class="main-nav"`, which this task's `base.html` rewrite removes (replaced
by `.primary-nav`/`.nav-item`). Update it:

```python
def test_main_nav_present_on_tasks_page(client):
    response = client.get("/tasks")
    assert response.status_code == 200
    assert b'class="primary-nav"' in response.content
    assert b'href="/requirements"' in response.content
    assert b'href="/matrix"' in response.content
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_layout.py tests/test_navigation.py -v`
Expected: PASS

- [ ] **Step 8: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: all tests pass (existing template-content assertions elsewhere may
need no change since class names inside fragments like `_task_list_only.html`
are untouched by this task — only `base.html`, `app.css`, and the nav test
changed).

```bash
git add app/templates/base.html app/static/app.css app/routers/tasks.py app/routers/calendar.py app/routers/requirements.py app/routers/matrix.py tests/test_layout.py tests/test_navigation.py
git commit -m "feat: rebuild app shell with Product Ops dark theme"
```

---

### Task 3: Shared traceability status helper

**Files:**
- Create: `idea_space/app/services/traceability.py`
- Test: `idea_space/tests/test_traceability_status.py`

**Interfaces:**
- Consumes: `Requirement` model (from Task 1's `models.py`, specifically its `.stakeholders`/`.decisions`/`.risks`/`.tasks` relationships and `.status` field — all pre-existing from Slice 3a).
- Produces: `traceability_status(requirement: Requirement) -> str`, returning one of `"at_risk"`, `"verified"`, `"partial"`, `"draft"`. Consumed by Task 6 (requirements.py) and Task 7 (matrix.py).

- [ ] **Step 1: Write the failing tests**

Create `idea_space/tests/test_traceability_status.py`. This codebase's
tests use the `db_session` pytest fixture from `tests/conftest.py` (a
fresh in-memory SQLite session per test) rather than `app.db.SessionLocal`
directly — every test below takes `db_session` as a parameter, matching
the existing convention already used in e.g. `test_matrix.py`'s
`test_matrix_shows_linked_entities(client, db_session)`:

```python
from datetime import date

from app.models import Decision, Requirement, Risk, Stakeholder, Task
from app.seed import seed_default_workspace
from app.services.traceability import traceability_status


def _make_requirement(db_session, **overrides):
    workspace, user = seed_default_workspace(db_session)
    defaults = dict(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Req",
        status="draft",
    )
    defaults.update(overrides)
    requirement = Requirement(**defaults)
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)
    return requirement


def test_draft_status_when_no_links(db_session):
    requirement = _make_requirement(db_session, status="draft")
    assert traceability_status(requirement) == "draft"


def test_partial_status_when_some_links_but_not_verified(db_session):
    requirement = _make_requirement(db_session, status="in_progress")
    stakeholder = Stakeholder(
        workspace_id=requirement.workspace_id, name="Jane", role="Sponsor"
    )
    db_session.add(stakeholder)
    db_session.commit()
    requirement.stakeholders.append(stakeholder)
    db_session.commit()
    db_session.refresh(requirement)

    assert traceability_status(requirement) == "partial"


def test_verified_status_requires_status_and_full_coverage(db_session):
    requirement = _make_requirement(db_session, status="approved")
    stakeholder = Stakeholder(
        workspace_id=requirement.workspace_id, name="Jane", role="Sponsor"
    )
    decision = Decision(
        workspace_id=requirement.workspace_id,
        title="Ship it",
        decided_at=date(2026, 1, 1),
        decided_by="Jane",
    )
    task = Task(
        workspace_id=requirement.workspace_id,
        owner_id=requirement.owner_id,
        title="Build it",
        due_date=requirement.created_at,
    )
    db_session.add_all([stakeholder, decision, task])
    db_session.commit()

    requirement.stakeholders.append(stakeholder)
    requirement.decisions.append(decision)
    requirement.tasks.append(task)
    db_session.commit()
    db_session.refresh(requirement)

    assert traceability_status(requirement) == "verified"


def test_verified_requires_all_three_categories_not_just_status(db_session):
    requirement = _make_requirement(db_session, status="approved")
    stakeholder = Stakeholder(
        workspace_id=requirement.workspace_id, name="Jane", role="Sponsor"
    )
    db_session.add(stakeholder)
    db_session.commit()
    requirement.stakeholders.append(stakeholder)
    db_session.commit()
    db_session.refresh(requirement)

    # approved status but missing decisions/tasks links -> not verified
    assert traceability_status(requirement) == "partial"


def test_at_risk_overrides_verified_status(db_session):
    requirement = _make_requirement(db_session, status="approved")
    stakeholder = Stakeholder(
        workspace_id=requirement.workspace_id, name="Jane", role="Sponsor"
    )
    decision = Decision(
        workspace_id=requirement.workspace_id,
        title="Ship it",
        decided_at=date(2026, 1, 1),
        decided_by="Jane",
    )
    task = Task(
        workspace_id=requirement.workspace_id,
        owner_id=requirement.owner_id,
        title="Build it",
        due_date=requirement.created_at,
    )
    risk = Risk(
        workspace_id=requirement.workspace_id,
        title="Vendor delay",
        severity="high",
        status="open",
    )
    db_session.add_all([stakeholder, decision, task, risk])
    db_session.commit()

    requirement.stakeholders.append(stakeholder)
    requirement.decisions.append(decision)
    requirement.tasks.append(task)
    requirement.risks.append(risk)
    db_session.commit()
    db_session.refresh(requirement)

    assert traceability_status(requirement) == "at_risk"


def test_low_severity_open_risk_does_not_trigger_at_risk(db_session):
    requirement = _make_requirement(db_session, status="draft")
    risk = Risk(
        workspace_id=requirement.workspace_id,
        title="Minor risk",
        severity="low",
        status="open",
    )
    db_session.add(risk)
    db_session.commit()
    requirement.risks.append(risk)
    db_session.commit()
    db_session.refresh(requirement)

    assert traceability_status(requirement) == "partial"


def test_closed_high_severity_risk_does_not_trigger_at_risk(db_session):
    requirement = _make_requirement(db_session, status="draft")
    risk = Risk(
        workspace_id=requirement.workspace_id,
        title="Resolved risk",
        severity="high",
        status="closed",
    )
    db_session.add(risk)
    db_session.commit()
    requirement.risks.append(risk)
    db_session.commit()
    db_session.refresh(requirement)

    assert traceability_status(requirement) == "partial"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_traceability_status.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.traceability'`

- [ ] **Step 3: Write the implementation**

Check `idea_space/app/services/` for an existing `__init__.py` (it exists — `app/services/activity.py` and `app/services/recurrence.py` already live there). Create `idea_space/app/services/traceability.py`:

```python
from typing import Literal

from app.models import Requirement

TraceabilityStatus = Literal["at_risk", "verified", "partial", "draft"]

_VERIFIED_STATUSES = {"approved", "delivered"}


def traceability_status(requirement: Requirement) -> TraceabilityStatus:
    """Compute a requirement's traceability status from its links and status.

    Checked in order:
    1. at_risk  - any linked open, high-severity Risk.
    2. verified - requirement.status is approved/delivered AND has >=1 link
                  in every one of Stakeholders/Decisions/Tasks.
    3. partial  - at least one link in any category.
    4. draft    - zero links in every category.
    """
    if any(risk.severity == "high" and risk.status == "open" for risk in requirement.risks):
        return "at_risk"

    has_full_coverage = bool(requirement.stakeholders) and bool(requirement.decisions) and bool(
        requirement.tasks
    )
    if requirement.status in _VERIFIED_STATUSES and has_full_coverage:
        return "verified"

    has_any_link = bool(
        requirement.stakeholders or requirement.decisions or requirement.risks or requirement.tasks
    )
    if has_any_link:
        return "partial"

    return "draft"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_traceability_status.py -v`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: all tests pass

```bash
git add app/services/traceability.py tests/test_traceability_status.py
git commit -m "feat: add shared traceability status computation"
```

---

### Task 4: Tasks page — NOW/NEXT/DONE board, metrics, quick capture, blocked flag

**Files:**
- Modify: `idea_space/app/routers/tasks.py`
- Modify: `idea_space/app/routers/labels.py`
- Modify: `idea_space/app/templates/tasks/list.html`
- Create: `idea_space/app/templates/tasks/_board.html`
- Create: `idea_space/app/templates/tasks/_card.html`
- Modify: `idea_space/app/templates/tasks/_task_list_only.html` (kept, restyled empty-state class, for the archived list)
- `idea_space/app/templates/tasks/_row.html` is unchanged — kept as-is for the archived list only
- Test: `idea_space/tests/test_tasks.py`

**Interfaces:**
- Consumes: `Task.blocked` (Task 1), CSS classes from Task 2 (`.task-board` is NOT a real class defined in Task 2 — the board fragment's root id is `#task-board`, styled via the `.board-columns`/`.task-card`/`.metrics-row` classes already defined there).
- Produces: `PATCH /tasks/{id}/block` (new endpoint); `tasks.py::_render_task_board(request, db) -> TemplateResponse` (new shared renderer, replaces the old pattern of each mutating endpoint independently rendering `_task_list_only.html`); every mutating task endpoint (`create_task`, `complete_task`, `archive_task`, `set_recurrence_active`, and `labels.py::assign_label`) now targets and returns this renderer's fragment, whose root is `<div id="task-board">`.

- [ ] **Step 1: Write the failing tests**

`idea_space/tests/test_tasks.py` already starts with `from datetime import
datetime, timedelta, timezone` and `UTC = timezone.utc`, and every test
function takes `client` (and `db_session` where it needs direct DB access)
as a pytest fixture parameter, per `tests/conftest.py` — match that
convention exactly, do not add a module-level `TestClient`. Append:

```python
def test_tasks_page_shows_metrics_row(client):
    due_today = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Today task", "due_date": due_today})

    response = client.get("/tasks")
    assert response.status_code == 200
    body = response.text
    assert 'class="metrics-row"' in body
    assert "OPEN" in body
    assert "IN FOCUS" in body
    assert "COMPLETED" in body
    assert "BLOCKED" in body


def test_task_due_today_lands_in_now_column_and_future_task_in_next(client):
    due_today = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    due_future = (datetime.now(UTC) + timedelta(days=5)).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Now task", "due_date": due_today})
    client.post("/tasks", data={"title": "Next task", "due_date": due_future})

    response = client.get("/tasks")
    body = response.text
    now_idx = body.index('data-board-column="now"')
    next_idx = body.index('data-board-column="next"')
    now_section = body[now_idx:next_idx]
    next_section = body[next_idx:]

    assert "Now task" in now_section
    assert "Next task" not in now_section
    assert "Next task" in next_section


def test_completed_task_lands_in_done_column(client, db_session):
    from app.models import Task

    due_today = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Finish me", "due_date": due_today})
    task = db_session.query(Task).filter_by(title="Finish me").one()
    client.post(f"/tasks/{task.id}/complete")

    response = client.get("/tasks")
    body = response.text
    done_idx = body.index('data-board-column="done"')
    assert "Finish me" in body[done_idx:]


def test_block_toggle_flips_and_is_reversible(client, db_session):
    from app.models import Task

    due_today = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Blockable", "due_date": due_today})
    task = db_session.query(Task).filter_by(title="Blockable").one()

    first = client.patch(f"/tasks/{task.id}/block")
    assert first.status_code == 200
    assert "task-card-blocked-badge" in first.text
    db_session.refresh(task)
    assert task.blocked is True

    second = client.patch(f"/tasks/{task.id}/block")
    assert second.status_code == 200
    db_session.refresh(task)
    assert task.blocked is False


def test_block_nonexistent_task_returns_404(client):
    response = client.patch("/tasks/999999/block")
    assert response.status_code == 404


def test_block_archived_task_returns_404(client, db_session):
    from app.models import Task

    due_today = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "To archive", "due_date": due_today})
    task = db_session.query(Task).filter_by(title="To archive").one()
    client.post(f"/tasks/{task.id}/complete")
    client.post(f"/tasks/{task.id}/archive")

    response = client.patch(f"/tasks/{task.id}/block")
    assert response.status_code == 404


def test_board_view_still_filters_by_label(client, db_session):
    # Regression check: the pre-redesign `/tasks?labels=X` filter (covered by
    # test_filter_tasks_by_label / test_filter_tasks_by_multiple_labels_is_or_matched
    # earlier in this file) must keep working now that the default view is
    # the NOW/NEXT/DONE board instead of a flat list.
    from app.models import Label, Task

    due_today = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Tagged task", "due_date": due_today})
    client.post("/tasks", data={"title": "Untagged task", "due_date": due_today})
    client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})
    label = db_session.query(Label).filter_by(name="Urgent").one()
    tagged = db_session.query(Task).filter_by(title="Tagged task").one()
    client.post(f"/tasks/{tagged.id}/labels", data={"label_id": label.id})

    response = client.get(f"/tasks?labels={label.id}")
    assert response.status_code == 200
    assert "Tagged task" in response.text
    assert "Untagged task" not in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tasks.py -v`
Expected: FAIL — no `metrics-row` markup, no `data-board-column` attribute, no `PATCH /tasks/{id}/block` route (404 becomes a routing 404 which happens to already match the "nonexistent task" test's expectation by accident, but the others fail), and the label-filter regression test fails because the board ignores `labels` entirely until Step 3.

- [ ] **Step 3: Add the shared board renderer and metrics/derivation logic to `tasks.py`**

Replace the full contents of `idea_space/app/routers/tasks.py` with:

```python
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ActivityLog, Label, Task
from app.routers import calendar as calendar_router
from app.seed import seed_default_workspace
from app.services.activity import record_change
from app.services.recurrence import compute_next_due_date

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

VALID_STATUSES = {"open", "done", "archived"}


def _normalize_due_date(task: Task) -> None:
    # SQLite strips tzinfo on read-back; normalize before comparing.
    if task.due_date.tzinfo is None:
        task.due_date = task.due_date.replace(tzinfo=timezone.utc)


def _attach_overdue_flag(tasks: list[Task]) -> list[Task]:
    now = datetime.now(timezone.utc)
    for task in tasks:
        _normalize_due_date(task)
        task.is_overdue = task.status == "open" and task.due_date < now
    return tasks


def _filtered_tasks(db: Session, label_ids: list[int] | None, status: str) -> list[Task]:
    query = db.query(Task).filter(Task.status == status)
    if label_ids:
        query = query.join(Task.labels).filter(Label.id.in_(label_ids)).distinct()
    tasks = query.order_by(Task.due_date.asc()).all()
    return _attach_overdue_flag(tasks)


def _open_tasks(db: Session) -> list[Task]:
    return _filtered_tasks(db, None, "open")


def _board_columns(open_tasks: list[Task], done_tasks: list[Task]) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    now_column = [t for t in open_tasks if t.due_date < today_end]
    next_column = [t for t in open_tasks if t.due_date >= today_end]
    done_column = sorted(
        done_tasks, key=lambda t: t.completed_at or t.created_at, reverse=True
    )[:10]

    return {"now": now_column, "next": next_column, "done": done_column, "today_start": today_start, "today_end": today_end}


def _task_metrics(db: Session, label_ids: list[int] | None = None) -> dict:
    open_query = db.query(Task).filter(Task.status == "open")
    done_query = db.query(Task).filter(Task.status == "done")
    if label_ids:
        open_query = open_query.join(Task.labels).filter(Label.id.in_(label_ids)).distinct()
        done_query = done_query.join(Task.labels).filter(Label.id.in_(label_ids)).distinct()

    open_tasks = _attach_overdue_flag(open_query.all())
    done_tasks = done_query.all()

    columns = _board_columns(open_tasks, done_tasks)

    open_count = len(open_tasks)
    in_focus_count = len(
        [t for t in open_tasks if columns["today_start"] <= t.due_date < columns["today_end"]]
    )
    completed_count = len(done_tasks)
    velocity = (
        round(completed_count / (completed_count + open_count) * 100)
        if (completed_count + open_count) > 0
        else 0
    )
    blocked_count = db.query(Task).filter(Task.blocked.is_(True)).count()

    return {
        "open_count": open_count,
        "in_focus_count": in_focus_count,
        "completed_count": completed_count,
        "velocity": velocity,
        "blocked_count": blocked_count,
        "columns": columns,
    }


def _render_task_board(request: Request, db: Session, label_ids: list[int] | None = None):
    metrics = _task_metrics(db, label_ids)
    all_labels = db.query(Label).order_by(Label.name.asc()).all()
    return templates.TemplateResponse(
        request,
        "tasks/_board.html",
        {
            "columns": metrics["columns"],
            "open_count": metrics["open_count"],
            "in_focus_count": metrics["in_focus_count"],
            "completed_count": metrics["completed_count"],
            "velocity": metrics["velocity"],
            "blocked_count": metrics["blocked_count"],
            "all_labels": all_labels,
            "selected_label_ids": label_ids or [],
        },
    )


@router.get("/tasks")
def list_tasks(
    request: Request,
    labels: str | None = None,
    status: str = "open",
    db: Session = Depends(get_db),
):
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    all_labels = db.query(Label).order_by(Label.name.asc()).all()
    label_ids = [int(x) for x in labels.split(",")] if labels else None

    if status == "archived":
        tasks = _filtered_tasks(db, label_ids, "archived")
        return templates.TemplateResponse(
            request,
            "tasks/list.html",
            {
                "show_archived": True,
                "tasks": tasks,
                "all_labels": all_labels,
                "selected_label_ids": label_ids or [],
                "active_nav": "tasks",
            },
        )

    metrics = _task_metrics(db, label_ids)
    return templates.TemplateResponse(
        request,
        "tasks/list.html",
        {
            "show_archived": False,
            "columns": metrics["columns"],
            "open_count": metrics["open_count"],
            "in_focus_count": metrics["in_focus_count"],
            "completed_count": metrics["completed_count"],
            "velocity": metrics["velocity"],
            "blocked_count": metrics["blocked_count"],
            "all_labels": all_labels,
            "selected_label_ids": label_ids or [],
            "active_nav": "tasks",
        },
    )


@router.post("/tasks")
def create_task(
    request: Request,
    title: str = Form(...),
    due_date: str = Form(...),
    recurrence_pattern: str | None = Form(None),
    recurrence_interval: int = Form(1),
    recurrence_days_of_week: str | None = Form(None),
    remind_at: str | None = Form(None),
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

    if remind_at:
        from app.models import Reminder

        parsed_remind_at = datetime.fromisoformat(remind_at).replace(tzinfo=timezone.utc)
        db.add(Reminder(task_id=task.id, remind_at=parsed_remind_at))
        db.commit()

    if recurrence_pattern:
        task.recurrence_series_id = task.id
        db.commit()

    return _render_task_board(request, db)


@router.post("/tasks/{task_id}/complete")
def complete_task(
    request: Request,
    task_id: int,
    completion_note: str | None = Form(None),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if task is None or task.status != "open":
        raise HTTPException(status_code=404, detail="Task not found or not open")

    record_change(db, task, "status", task.status, "done")
    task.status = "done"
    task.completed_at = datetime.now(timezone.utc)
    task.completion_note = completion_note or None
    db.commit()

    if task.recurrence_active:
        _normalize_due_date(task)

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

    return _render_task_board(request, db)


@router.post("/tasks/{task_id}/archive")
def archive_task(request: Request, task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None or task.status != "done":
        raise HTTPException(status_code=404, detail="Task not found or not done")

    record_change(db, task, "status", "done", "archived")
    task.status = "archived"
    db.commit()

    return _render_task_board(request, db)


@router.get("/tasks/{task_id}/history")
def task_history(request: Request, task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    entries = (
        db.query(ActivityLog)
        .filter(ActivityLog.task_id == task_id)
        .order_by(ActivityLog.changed_at.desc(), ActivityLog.id.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "tasks/_history.html",
        {"task_id": task_id, "entries": entries, "completion_note": task.completion_note},
    )


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

    return _render_task_board(request, db)


@router.patch("/tasks/{task_id}/block")
def toggle_blocked(request: Request, task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None or task.status == "archived":
        raise HTTPException(status_code=404, detail="Task not found")

    task.blocked = not task.blocked
    db.commit()

    return _render_task_board(request, db)


@router.patch("/tasks/{task_id}/reschedule")
def reschedule_task(
    request: Request,
    task_id: int,
    due_date: str = Form(...),
    view: str = Form("month"),
    month: str | None = Form(None),
    start: str | None = Form(None),
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

    return calendar_router.render_calendar(request, db, view=view, month=month, start=start)
```

Note: `reschedule_task` now calls `calendar_router.render_calendar(...)`, a
function Task 5 adds — this task's own tests don't exercise the calendar
path, but leave this call in place since Task 5 depends on it existing here
verbatim (same function name/signature) and this task compiles fine as long
as Task 5 lands before anyone hits `/tasks/{id}/reschedule` in the running
app (the existing `calendar.py::calendar_week` function this replaced is
removed in Task 5, not here — see Task 5 Step 3).

- [ ] **Step 4: Update `labels.py`'s `assign_label` to use the shared renderer**

In `idea_space/app/routers/labels.py`, replace the body of `assign_label`:

```python
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

    from app.routers.tasks import _render_task_board

    return _render_task_board(request, db)
```

(Remove the now-unused `from app.routers.tasks import _open_tasks` import
that lived inside the old function body — there is no longer a module-level
import to touch since it was already function-local.)

- [ ] **Step 5: Create the board template**

Create `idea_space/app/templates/tasks/_board.html`:

```html
<div id="task-board">
  <div class="metrics-row">
    <div class="metric-card">
      <span class="metric-label">OPEN</span>
      <div class="metric-value-row">
        <span class="metric-value">{{ "%02d"|format(open_count) }}</span>
      </div>
    </div>
    <div class="metric-card">
      <span class="metric-label">IN FOCUS</span>
      <div class="metric-value-row">
        <span class="metric-value">{{ "%02d"|format(in_focus_count) }}</span>
        <span class="metric-note metric-note--warning">Due today</span>
      </div>
    </div>
    <div class="metric-card">
      <span class="metric-label">COMPLETED</span>
      <div class="metric-value-row">
        <span class="metric-value">{{ "%02d"|format(completed_count) }}</span>
        <span class="metric-note metric-note--success">{{ velocity }}% velocity</span>
      </div>
    </div>
    <div class="metric-card">
      <span class="metric-label">BLOCKED</span>
      <div class="metric-value-row">
        <span class="metric-value">{{ "%02d"|format(blocked_count) }}</span>
        {% if blocked_count > 0 %}<span class="metric-note metric-note--danger">Needs review</span>{% endif %}
      </div>
    </div>
  </div>

  <div class="quick-capture">
    <div class="quick-capture-icon">+</div>
    <form hx-post="/tasks" hx-target="#task-board" hx-swap="outerHTML" class="quick-capture-fields" style="display:flex;">
      <div class="quick-capture-fields">
        <span class="quick-capture-label">CAPTURE AN IDEA</span>
        <input type="text" name="title" class="quick-capture-input" placeholder="What needs your attention?" required>
        <input type="hidden" name="due_date" value="{{ today_iso }}">
      </div>
      <button type="submit" style="display:none;" aria-hidden="true">Add</button>
    </form>
    <span class="quick-capture-meta">Press Enter</span>
  </div>

  {% include "labels/_filter_bar.html" %}

  <nav class="filter-bar">
    {% for label in all_labels|default([]) %}
    <a href="/tasks?labels={{ label.id }}"
       class="label-chip{% if label.id in selected_label_ids|default([]) %} label-chip--active{% endif %}"
       style="background-color: {{ label.color }};">{{ label.name }}</a>
    {% endfor %}
    <a href="/tasks">Clear filters</a>
  </nav>

  <div class="board-columns">
    <div class="board-column" data-board-column="now">
      <div class="board-column-header">
        <div class="board-column-label-group">
          <span class="board-column-dot board-column-dot--now"></span>
          <span class="board-column-label">NOW</span>
        </div>
        <span class="board-column-count">{{ columns.now|length }} tasks</span>
      </div>
      {% for task in columns.now %}
        {% include "tasks/_card.html" %}
      {% endfor %}
    </div>
    <div class="board-column" data-board-column="next">
      <div class="board-column-header">
        <div class="board-column-label-group">
          <span class="board-column-dot board-column-dot--next"></span>
          <span class="board-column-label">NEXT</span>
        </div>
        <span class="board-column-count">{{ columns.next|length }} tasks</span>
      </div>
      {% for task in columns.next %}
        {% include "tasks/_card.html" %}
      {% endfor %}
    </div>
    <div class="board-column" data-board-column="done">
      <div class="board-column-header">
        <div class="board-column-label-group">
          <span class="board-column-dot board-column-dot--done"></span>
          <span class="board-column-label">DONE</span>
        </div>
        <span class="board-column-count">{{ columns.done|length }} tasks</span>
      </div>
      {% for task in columns.done %}
        {% include "tasks/_card.html" %}
      {% endfor %}
    </div>
  </div>

  <p><a class="archived-link" href="/tasks?status=archived">View archived tasks &rarr;</a></p>
</div>
```

The `today_iso` variable referenced in the hidden `due_date` field isn't
passed by `_render_task_board` — replace that hidden input with a small
inline script instead, since the quick-capture bar has no server-computed
"today" available at render time without adding it to every board
response. Change the `<input type="hidden" ...>` line to:

```html
        <input type="hidden" name="due_date" class="js-today-due-date">
```

And add, right before `</div>` that closes `#task-board` (i.e. as the last
line inside the root div, after the archived-link paragraph):

```html
  <script>
    document.querySelectorAll(".js-today-due-date").forEach(function (el) {
      if (!el.value) {
        el.value = new Date().toISOString().slice(0, 16);
      }
    });
  </script>
```

This runs once per swap (htmx re-executes `<script>` tags in swapped
content), which is exactly what's needed since the board fragment is
re-rendered on every mutation.

- [ ] **Step 6: Create the card partial**

Create `idea_space/app/templates/tasks/_card.html`:

```html
<div class="task-card{% if task.status == 'done' %} task-card--done{% endif %}" data-task-id="{{ task.id }}">
  <div class="task-card-title-row">
    {% if task.status == "open" %}
    <form hx-post="/tasks/{{ task.id }}/complete" hx-target="#task-board" hx-swap="outerHTML" style="display:contents;">
      <input type="checkbox" class="task-card-checkbox" onclick="this.form.requestSubmit()">
    </form>
    {% else %}
    <input type="checkbox" class="task-card-checkbox" checked disabled>
    {% endif %}
    <span class="task-card-title">{{ task.title }}</span>
  </div>
  <div class="task-card-meta">
    <div style="display:flex; gap:6px; align-items:center;">
      {% for label in task.labels %}
      <span class="task-card-tag" style="background-color: {{ label.color }};">{{ label.name }}</span>
      {% endfor %}
      {% if task.blocked %}
      <span class="task-card-blocked-badge">BLOCKED</span>
      {% endif %}
    </div>
    <span class="task-card-due{% if task.status == 'done' %} task-card-due--done{% endif %}">
      {% if task.status == "done" %}Done{% else %}{{ task.due_date.strftime('%b %d') }}{% endif %}
    </span>
  </div>
  <div class="task-card-actions">
    <button hx-patch="/tasks/{{ task.id }}/block" hx-target="#task-board" hx-swap="outerHTML">
      {{ "Unblock" if task.blocked else "Block" }}
    </button>
    {% if task.recurrence_pattern %}
    <button hx-patch="/tasks/{{ task.id }}/recurrence" hx-vals='{"active": "{{ "false" if task.recurrence_active else "true" }}"}' hx-target="#task-board" hx-swap="outerHTML">
      {{ "Pause" if task.recurrence_active else "Resume" }}
    </button>
    {% endif %}
    {% if all_labels %}
    <form hx-post="/tasks/{{ task.id }}/labels" hx-target="#task-board" hx-swap="outerHTML" style="display:inline">
      <select name="label_id">
        {% for label in all_labels %}
        <option value="{{ label.id }}">{{ label.name }}</option>
        {% endfor %}
      </select>
      <button type="submit">Add label</button>
    </form>
    {% endif %}
    {% if task.status == "done" %}
    <button hx-post="/tasks/{{ task.id }}/archive" hx-target="#task-board" hx-swap="outerHTML">Archive</button>
    {% endif %}
    <button hx-get="/tasks/{{ task.id }}/history" hx-target="#history-{{ task.id }}" hx-swap="outerHTML">History</button>
  </div>
  <div id="history-{{ task.id }}" class="task-history"></div>
</div>
```

- [ ] **Step 7: Update `tasks/list.html` to branch on archived vs. board view**

Replace the full contents of `idea_space/app/templates/tasks/list.html`:

```html
{% extends "base.html" %}
{% block content %}
<div class="page-header">
  <div>
    <div class="page-eyebrow">COMMAND CENTER</div>
    <div class="page-title">{% if show_archived %}Archived tasks{% else %}Today's priorities{% endif %}</div>
    <div class="page-subtitle">Turn loose ideas into visible progress.</div>
  </div>
</div>

{% if show_archived %}
  {% include "labels/_filter_bar.html" %}
  {% include "tasks/_task_list_only.html" %}
  <p><a class="archived-link" href="/tasks">&larr; Back to board</a></p>
{% else %}
  {% include "tasks/_board.html" %}
{% endif %}
{% endblock %}
```

- [ ] **Step 8: Restyle the archived-list partials (functionality unchanged)**

Modify `idea_space/app/templates/tasks/_task_list_only.html`:

```html
<ul id="task-list">
  {% if not tasks %}
  <p class="agenda-empty">No archived tasks.</p>
  {% else %}
  {% for task in tasks %}
    {% include "tasks/_row.html" %}
  {% endfor %}
  {% endif %}
</ul>
```

Modify `idea_space/app/templates/tasks/_row.html` (unchanged logic, only
the wrapping list-item class stays as-is since `.task`/`.task--overdue`/
`.task--virtual` are still defined in Task 2's CSS for this archived-list
fallback — no template change needed here at all; skip this file).

- [ ] **Step 9: Run tests to verify they pass**

Run: `python -m pytest tests/test_tasks.py -v`
Expected: PASS (all new and existing tests)

- [ ] **Step 10: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: all tests pass — pay particular attention to any existing test in
`test_tasks.py` or `test_labels.py` that asserted on `#task-list` being the
response root for `POST /tasks`, `POST /tasks/{id}/complete`,
`POST /tasks/{id}/archive`, `PATCH /tasks/{id}/recurrence`, or
`POST /tasks/{id}/labels` — those now return `#task-board` instead, so any
such assertion needs updating to match (update it in this same commit; this
is exactly the kind of contract change Slice 1-3a's final reviews have
caught before — fix it proactively here).

```bash
git add app/routers/tasks.py app/routers/labels.py app/templates/tasks/ tests/test_tasks.py
git commit -m "feat: rebuild tasks page as NOW/NEXT/DONE board with metrics"
```

---

### Task 5: Calendar — month/week/agenda views and fragment-safe reschedule

**Files:**
- Modify: `idea_space/app/routers/calendar.py`
- Delete: `idea_space/app/templates/calendar/week.html` (superseded by `index.html` + `_week.html`)
- Create: `idea_space/app/templates/calendar/_month.html`
- Create: `idea_space/app/templates/calendar/_week.html`
- Create: `idea_space/app/templates/calendar/_agenda.html`
- Create: `idea_space/app/templates/calendar/index.html`
- Modify: `idea_space/app/static/app.js`
- Modify: `idea_space/app/routers/tasks.py` (fix `reschedule_task` to call the fragment renderer this task defines)
- Modify: `idea_space/tests/test_calendar.py` (already exists from Slice 1)

**Interfaces:**
- Consumes: `calendar_router.render_calendar(request, db, view, month, start)` is called by Task 4's `reschedule_task` — this task MUST define a function with exactly that name and signature.
- Produces: `GET /calendar?view=month|week|agenda&month=YYYY-MM&start=YYYY-MM-DD` (400 on an invalid `view`); `render_calendar(request, db, view="month", month=None, start=None)` returning a full-page `TemplateResponse`; a second dispatcher `_render_calendar_fragment(request, db, view, month, start)` returning just the `#calendar-content` fragment (used by the reschedule PATCH response).

- [ ] **Step 1: Write the failing tests**

`idea_space/tests/test_calendar.py` already exists (from Slice 1) with 4
tests using the `client`/`db_session` fixtures from `tests/conftest.py`
and calling `GET /calendar?start=2026-09-21` expecting the (until now,
only) week view. Since this task makes `view` default to `"month"`, those
4 existing tests need `&view=week` added to their query string or they'll
silently start asserting against month-view output instead — **fix them
in this same step**, then append the new tests. The file becomes:

```python
from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def test_calendar_week_shows_real_task_on_its_day(client):
    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)  # Tuesday
    client.post(
        "/tasks",
        data={"title": "Stakeholder sync", "due_date": due.strftime("%Y-%m-%dT%H:%M")},
    )

    response = client.get("/calendar?view=week&start=2026-09-21")
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
    response = client.get("/calendar?view=week&start=2026-09-21")
    assert b"task--virtual" in response.content
    assert b"Weekly status update" in response.content


def test_calendar_week_lists_overdue_tasks_from_before_the_range(client):
    overdue_due = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    client.post(
        "/tasks",
        data={"title": "Send follow-up email", "due_date": overdue_due.strftime("%Y-%m-%dT%H:%M")},
    )

    response = client.get("/calendar?view=week&start=2026-09-21")
    assert b"Send follow-up email" in response.content
    assert b"calendar-overdue" in response.content


def test_calendar_excludes_archived_tasks(client, db_session):
    from app.models import Task

    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    client.post("/tasks", data={"title": "Old task", "due_date": due.strftime("%Y-%m-%dT%H:%M")})
    task = db_session.query(Task).filter_by(title="Old task").one()
    client.post(f"/tasks/{task.id}/complete")
    client.post(f"/tasks/{task.id}/archive")

    response = client.get("/calendar?view=week&start=2026-09-21")
    assert b"Old task" not in response.content


def test_calendar_defaults_to_month_view(client):
    response = client.get("/calendar")
    assert response.status_code == 200
    assert 'data-view="month"' in response.text


def test_calendar_month_view_pads_to_full_weeks(client):
    # September 2026 starts on a Tuesday and has 30 days -> 5 rows of 7 = 35 cells.
    response = client.get("/calendar?view=month&month=2026-09")
    assert response.status_code == 200
    assert response.text.count('class="calendar-day') == 35


def test_calendar_week_view_still_works(client):
    response = client.get("/calendar?view=week")
    assert response.status_code == 200
    assert 'data-view="week"' in response.text


def test_calendar_agenda_view_shows_only_next_14_days(client):
    within_range = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%dT12:00")
    out_of_range = (datetime.now(UTC) + timedelta(days=20)).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Soon task", "due_date": within_range})
    client.post("/tasks", data={"title": "Far task", "due_date": out_of_range})

    response = client.get("/calendar?view=agenda")
    assert response.status_code == 200
    assert 'data-view="agenda"' in response.text
    assert "Soon task" in response.text
    assert "Far task" not in response.text


def test_calendar_invalid_view_returns_400(client):
    response = client.get("/calendar?view=bogus")
    assert response.status_code == 400


def test_reschedule_returns_matching_fragment_for_requested_view(client, db_session):
    from app.models import Task

    due_date = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Move me", "due_date": due_date})
    task = db_session.query(Task).filter_by(title="Move me").one()

    new_date = (datetime.now(UTC) + timedelta(days=2)).strftime("%Y-%m-%d")
    response = client.patch(
        f"/tasks/{task.id}/reschedule",
        data={"due_date": new_date, "view": "agenda"},
    )
    assert response.status_code == 200
    assert 'id="calendar-content"' in response.text
    assert 'data-view="agenda"' in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_calendar.py -v`
Expected: FAIL — `view` query param doesn't exist yet, no month/agenda
templates, `render_calendar` doesn't exist. (The 4 pre-existing tests,
now with `view=week` added, still fail too, since `view` isn't recognized
until Step 3 — that's expected and resolves once Step 3 lands.)

- [ ] **Step 3: Rewrite `calendar.py`**

Replace the full contents of `idea_space/app/routers/calendar.py` with:

```python
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
```

Note: `render_calendar` returns the **full page** (used by `GET /calendar`
and reused by Task 4's `reschedule_task` — wait, re-check Task 4: it calls
`calendar_router.render_calendar(...)` and returns that directly as the
endpoint's response for `PATCH /tasks/{id}/reschedule`. That would return a
full page into a `fetch()`-driven `innerHTML`/`outerHTML` swap, which is
exactly the bug the spec calls out fixing. **Fix it now**: go back and
change Task 4's `reschedule_task` to call
`calendar_router._render_calendar_fragment(...)` instead of
`calendar_router.render_calendar(...)` — update that one line in
`idea_space/app/routers/tasks.py` as part of this task's commit, since this
task is what defines `_render_calendar_fragment` and is responsible for
wiring reschedule to the fragment-only response:

```python
    return calendar_router._render_calendar_fragment(request, db, view=view, month=month, start=start)
```

- [ ] **Step 4: Create `calendar/index.html`**

Create `idea_space/app/templates/calendar/index.html`:

```html
{% extends "base.html" %}
{% block content %}
<div class="page-header">
  <div>
    <div class="page-eyebrow">PLANNING HORIZON</div>
    <div class="page-title">
      {% if view == "month" %}{{ month_label }}{% elif view == "week" %}Week of {{ week_start.strftime('%b %d, %Y') }}{% else %}Upcoming agenda{% endif %}
    </div>
    <div class="page-subtitle">A calm view of commitments, milestones, and momentum.</div>
  </div>
  <div class="calendar-view-toggle">
    <a class="calendar-view-btn{% if view == 'month' %} calendar-view-btn--active{% endif %}" href="/calendar?view=month">MONTH</a>
    <a class="calendar-view-btn{% if view == 'week' %} calendar-view-btn--active{% endif %}" href="/calendar?view=week">WEEK</a>
    <a class="calendar-view-btn{% if view == 'agenda' %} calendar-view-btn--active{% endif %}" href="/calendar?view=agenda">AGENDA</a>
  </div>
</div>
<div class="calendar-layout">
  <div class="calendar-main">
    {% include content_template %}
  </div>
  <div class="upcoming-agenda">
    <div class="page-eyebrow">UP NEXT</div>
    {% if upcoming %}
    <div style="font-size:19px; font-weight:600;">{{ upcoming.date.strftime('%A, %b %d') }}</div>
    {% for item in upcoming.items %}
    <div class="calendar-agenda-item" style="border:none; padding:0;">
      <div class="calendar-event-marker" style="background: {{ ['#33D69F', '#A855F7', '#F5B942', '#9A9AA3'][loop.index0 % 4] }};"></div>
      <div>
        <div style="font-size:9px; font-weight:700;">{{ item.due_date.strftime('%H:%M') }}</div>
        <div style="font-size:12px; font-weight:600;">{{ item.title }}</div>
      </div>
    </div>
    {% endfor %}
    {% else %}
    <p class="agenda-empty">Nothing scheduled.</p>
    {% endif %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Create `calendar/_month.html`**

Create `idea_space/app/templates/calendar/_month.html`:

```html
<div id="calendar-content" data-view="month" data-month="{{ month_str }}">
  <div class="calendar-toolbar">
    <div style="display:flex; gap:8px; align-items:center;">
      <a class="btn btn-outline" href="/calendar?view=month&month={{ (month_start.replace(day=1) - timedelta(days=1)).strftime('%Y-%m') if false else '' }}">&lsaquo;</a>
    </div>
    <a class="btn btn-outline" href="/calendar?view=month">TODAY</a>
  </div>
  <div class="calendar-weekday-row">
    <div class="calendar-weekday">MON</div>
    <div class="calendar-weekday">TUE</div>
    <div class="calendar-weekday">WED</div>
    <div class="calendar-weekday">THU</div>
    <div class="calendar-weekday">FRI</div>
    <div class="calendar-weekday">SAT</div>
    <div class="calendar-weekday">SUN</div>
  </div>
  <div class="calendar-month-grid">
    {% for week in weeks %}
      {% for day in week %}
      <div class="calendar-day{% if day.is_today %} calendar-day--today{% endif %}{% if not day.is_current_month %} calendar-day--other-month{% endif %}" data-date="{{ day.date.strftime('%Y-%m-%d') }}">
        <div class="calendar-day-number">{{ day.date.day }}</div>
        <ul>
          {% for item in day.items %}
          <li class="calendar-event{% if item.virtual %} task--virtual{% endif %}" {% if not item.virtual %}data-task-id="{{ item.id }}" draggable="true"{% endif %}>
            <span class="calendar-event-marker" style="background: var(--accent);"></span>
            <span class="calendar-event-name">{{ item.title }}</span>
          </li>
          {% endfor %}
        </ul>
      </div>
      {% endfor %}
    {% endfor %}
  </div>
</div>
```

The stray `{{ (month_start.replace(day=1) - timedelta(days=1))... if false else '' }}`
prev/next-month navigation expression above is intentionally inert — remove
that whole `<div style="display:flex...">...</div>` block entirely; prev/
next month navigation isn't in the spec's scope (only TODAY is meaningful
here, matching the mockup's own toolbar, which does show `<` `>` but this
plan keeps only the working TODAY control to avoid a half-built feature).
Replace Step 5's toolbar block with:

```html
  <div class="calendar-toolbar">
    <span style="font-size:11px; font-weight:700;">{{ month_label }}</span>
    <a class="btn btn-outline" href="/calendar?view=month">TODAY</a>
  </div>
```

- [ ] **Step 6: Create `calendar/_week.html`**

Create `idea_space/app/templates/calendar/_week.html` (restyled version of
the previous `calendar/week.html` content, now a fragment rather than a
full page):

```html
<div id="calendar-content" data-view="week" data-week-start="{{ week_start_str }}">
  {% if overdue %}
  <div class="calendar-overdue">
    <h3>Overdue</h3>
    <ul style="list-style:none; padding:0; margin:0;">
      {% for task in overdue %}
      <li class="calendar-event" data-task-id="{{ task.id }}" draggable="true">
        <span class="calendar-event-marker" style="background: var(--danger);"></span>
        <span class="calendar-event-name">{{ task.title }} &mdash; {{ task.due_date.strftime('%Y-%m-%d') }}</span>
      </li>
      {% endfor %}
    </ul>
  </div>
  {% endif %}
  <div class="calendar-weekday-row">
    {% for day in days %}
    <div class="calendar-weekday">{{ day.date.strftime('%a %b %d') }}</div>
    {% endfor %}
  </div>
  <div class="calendar-week">
    {% for day in days %}
    <div class="calendar-day" data-date="{{ day.date.strftime('%Y-%m-%d') }}">
      <ul>
        {% for item in day.items %}
        <li class="calendar-event{% if item.virtual %} task--virtual{% endif %}" {% if not item.virtual %}data-task-id="{{ item.id }}" draggable="true"{% endif %}>
          <span class="calendar-event-marker" style="background: var(--accent);"></span>
          <span class="calendar-event-name">{{ item.title }}</span>
        </li>
        {% endfor %}
      </ul>
    </div>
    {% endfor %}
  </div>
</div>
```

Delete `idea_space/app/templates/calendar/week.html` (fully superseded by
`calendar/index.html` + `calendar/_week.html`).

- [ ] **Step 7: Create `calendar/_agenda.html`**

Create `idea_space/app/templates/calendar/_agenda.html`:

```html
<div id="calendar-content" data-view="agenda">
  {% if not items %}
  <p class="agenda-empty">Nothing scheduled in the next 14 days.</p>
  {% else %}
  <ul class="calendar-agenda-list">
    {% for item in items %}
    <li class="calendar-agenda-item">
      <span class="calendar-event-marker" style="background: var(--accent);"></span>
      <div>
        <div style="font-size:9px; font-weight:700; color: var(--text-muted);">{{ item.due_date.strftime('%a %b %d, %H:%M') }}</div>
        <div style="font-size:12px; font-weight:600;">{{ item.title }}</div>
      </div>
    </li>
    {% endfor %}
  </ul>
  {% endif %}
</div>
```

- [ ] **Step 8: Update `app.js`'s drag-reschedule handler**

Replace the full contents of `idea_space/app/static/app.js`:

```javascript
document.body.addEventListener("dragstart", (event) => {
  const taskEl = event.target.closest("[data-task-id]");
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

  const contentEl = document.getElementById("calendar-content");
  if (!contentEl) return;

  const newDate = dayEl.dataset.date;
  const params = new URLSearchParams();
  params.set("due_date", newDate);
  params.set("view", contentEl.dataset.view || "month");
  if (contentEl.dataset.month) params.set("month", contentEl.dataset.month);
  if (contentEl.dataset.weekStart) params.set("start", contentEl.dataset.weekStart);

  const response = await fetch(`/tasks/${taskId}/reschedule`, {
    method: "PATCH",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: params.toString(),
  });

  if (response.ok) {
    const html = await response.text();
    contentEl.outerHTML = html;
  }
});
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `python -m pytest tests/test_calendar.py -v`
Expected: PASS

- [ ] **Step 10: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: all tests pass — check for any pre-existing calendar test that
asserted on the old `calendar/week.html` full-page structure (e.g.
`class="calendar-week"` as the response's top-level element for
`GET /calendar`); update it to match the new `calendar/index.html`
wrapper + `#calendar-content` fragment structure.

```bash
git add app/routers/calendar.py app/routers/tasks.py app/templates/calendar/ app/static/app.js tests/test_calendar.py
git commit -m "feat: add month/agenda calendar views, fix reschedule fragment swap"
```

---

### Task 6: Requirements — dashboard metrics, filters, CSV export

**Files:**
- Modify: `idea_space/app/routers/requirements.py`
- Modify: `idea_space/app/templates/requirements/list.html`
- Modify: `idea_space/app/templates/requirements/_row.html`
- Modify: `idea_space/app/templates/requirements/_list_only.html`
- Test: `idea_space/tests/test_requirements.py`

**Interfaces:**
- Consumes: `Requirement.updated_at` (Task 1), `traceability_status` (Task 3).
- Produces: `GET /requirements?filter=all|active|archived` (400 on invalid); `GET /requirements/export.csv`.

- [ ] **Step 1: Write the failing tests**

Append to `idea_space/tests/test_requirements.py`, matching its existing
convention (already established from Slice 3a) of taking `client` and
`db_session` as pytest fixture parameters rather than a module-level
client or `app.db.SessionLocal`:

```python
def test_requirements_page_shows_metrics_row(client):
    response = client.get("/requirements")
    assert response.status_code == 200
    body = response.text
    assert 'class="metrics-row"' in body
    assert "TOTAL" in body
    assert "VALIDATED" in body
    assert "IN REVIEW" in body
    assert "AT RISK" in body


def test_requirements_filter_invalid_value_returns_400(client):
    response = client.get("/requirements?filter=bogus")
    assert response.status_code == 400


def test_requirements_filter_archived_shows_only_delivered(client):
    client.post("/requirements", data={"title": "Draft one", "status": "draft"})
    client.post("/requirements", data={"title": "Shipped one", "status": "delivered"})

    response = client.get("/requirements?filter=archived")
    assert response.status_code == 200
    assert "Shipped one" in response.text
    assert "Draft one" not in response.text


def test_edit_requirement_updates_updated_at(client, db_session):
    from datetime import timezone

    from app.models import Requirement

    client.post("/requirements", data={"title": "Editable"})
    requirement = db_session.query(Requirement).filter_by(title="Editable").one()
    before = requirement.updated_at
    if before.tzinfo is None:
        before = before.replace(tzinfo=timezone.utc)

    client.patch(
        f"/requirements/{requirement.id}",
        data={"title": "Editable v2", "status": "draft"},
    )

    db_session.refresh(requirement)
    after = requirement.updated_at
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)
    assert after >= before


def test_requirements_export_csv_returns_one_row_per_requirement(client):
    client.post("/requirements", data={"title": "CSV req"})

    response = client.get("/requirements/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    lines = response.text.strip().splitlines()
    assert lines[0] == "id,title,status,owner,updated_at,links_count"
    assert any("CSV req" in line for line in lines[1:])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_requirements.py -v`
Expected: FAIL — no metrics row, no `filter` param, no export route.

- [ ] **Step 3: Update `requirements.py`**

In `idea_space/app/routers/requirements.py`, add the import and helper,
then update `list_requirements`, `create_requirement`, and
`edit_requirement`:

```python
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
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
from app.services.traceability import traceability_status

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

VALID_REQUIREMENT_STATUSES = {"draft", "approved", "in_progress", "delivered"}
VALID_FILTERS = {"all", "active", "archived"}


def _all_requirements(db: Session) -> list[Requirement]:
    return db.query(Requirement).order_by(Requirement.updated_at.desc()).all()


def _requirement_page_context(db: Session, requirement: Requirement) -> dict:
    return {
        "requirement": requirement,
        "all_stakeholders": db.query(Stakeholder).order_by(Stakeholder.name.asc()).all(),
        "all_decisions": db.query(Decision).order_by(Decision.title.asc()).all(),
        "all_risks": db.query(Risk).order_by(Risk.title.asc()).all(),
        "all_tasks": db.query(Task).order_by(Task.title.asc()).all(),
    }


def _links_count(requirement: Requirement) -> int:
    return (
        len(requirement.stakeholders)
        + len(requirement.decisions)
        + len(requirement.risks)
        + len(requirement.tasks)
    )


@router.get("/requirements")
def list_requirements(
    request: Request, filter: str = "all", db: Session = Depends(get_db)
):
    if filter not in VALID_FILTERS:
        raise HTTPException(status_code=400, detail=f"Invalid filter: {filter}")

    all_requirements = _all_requirements(db)

    total_count = len(all_requirements)
    validated_count = sum(1 for r in all_requirements if traceability_status(r) == "verified")
    in_review_count = sum(1 for r in all_requirements if r.status == "in_progress")
    at_risk_count = sum(1 for r in all_requirements if traceability_status(r) == "at_risk")
    active_count = sum(1 for r in all_requirements if r.status != "delivered")
    archived_count = total_count - active_count

    if filter == "active":
        visible = [r for r in all_requirements if r.status != "delivered"]
    elif filter == "archived":
        visible = [r for r in all_requirements if r.status == "delivered"]
    else:
        visible = all_requirements

    return templates.TemplateResponse(
        request,
        "requirements/list.html",
        {
            "requirements": visible,
            "all_stakeholders": db.query(Stakeholder).order_by(Stakeholder.name.asc()).all(),
            "all_decisions": db.query(Decision).order_by(Decision.title.asc()).all(),
            "all_risks": db.query(Risk).order_by(Risk.title.asc()).all(),
            "total_count": total_count,
            "validated_count": validated_count,
            "in_review_count": in_review_count,
            "at_risk_count": at_risk_count,
            "active_count": active_count,
            "archived_count": archived_count,
            "current_filter": filter,
            "traceability_status": traceability_status,
            "active_nav": "requirements",
        },
    )


@router.get("/requirements/export.csv")
def export_requirements_csv(db: Session = Depends(get_db)):
    requirements = _all_requirements(db)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "title", "status", "owner", "updated_at", "links_count"])
    for requirement in requirements:
        writer.writerow(
            [
                requirement.id,
                requirement.title,
                requirement.status,
                requirement.owner_id,
                requirement.updated_at.isoformat(),
                _links_count(requirement),
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=requirements.csv"},
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
        request,
        "requirements/_list_only.html",
        {"requirements": _all_requirements(db), "traceability_status": traceability_status},
    )
```

Then in `edit_requirement`, add `requirement.updated_at =
datetime.now(timezone.utc)` right before `db.commit()`:

```python
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
    requirement.updated_at = datetime.now(timezone.utc)
    db.commit()

    return templates.TemplateResponse(
        request, "requirements/_page.html", _requirement_page_context(db, requirement)
    )
```

Leave `requirement_detail`, `delete_requirement`, and all `link_*`/`unlink_*`
endpoints unchanged except adding `"active_nav": "requirements"` to
`requirement_detail`'s returned context dict (it currently returns
`_requirement_page_context(db, requirement)` directly — wrap it:
`{**_requirement_page_context(db, requirement), "active_nav": "requirements"}`).

- [ ] **Step 4: Update `requirements/_row.html`**

Replace `idea_space/app/templates/requirements/_row.html`:

```html
<li class="requirement" data-requirement-id="{{ requirement.id }}">
  <span class="requirement-id">REQ-{{ "%03d"|format(requirement.id) }}</span>
  <div class="requirement-main">
    <a href="/requirements/{{ requirement.id }}" class="requirement-title">{{ requirement.title }}</a>
    <span class="requirement-meta">Updated {{ requirement.updated_at.strftime('%Y-%m-%d') }}</span>
  </div>
  <span class="requirement-owner">Owner</span>
  <span class="requirement-status">
    {% set trace_status = traceability_status(requirement) %}
    {% if trace_status == "at_risk" %}
    <span class="status-badge status-badge--danger">AT RISK</span>
    {% elif trace_status == "verified" %}
    <span class="status-badge status-badge--success">VALIDATED</span>
    {% elif trace_status == "partial" %}
    <span class="status-badge status-badge--warning">PARTIAL</span>
    {% else %}
    <span class="status-badge status-badge--neutral">DRAFT</span>
    {% endif %}
  </span>
  <span class="requirement-links">{{ "%02d"|format(requirement.stakeholders|length + requirement.decisions|length + requirement.risks|length + requirement.tasks|length) }}</span>
</li>
```

`Owner` is a fixed placeholder text (Non-Goal: no multi-user picker exists
yet — every requirement's `owner_id` is the single seeded user, so naming
it dynamically adds a query for no real information yet; a later slice
that adds multi-user support replaces this literal).

- [ ] **Step 5: Update `requirements/_list_only.html`**

```html
<ul id="requirement-list">
  {% if not requirements %}
  <p class="agenda-empty">No requirements yet — add one above.</p>
  {% else %}
  {% for requirement in requirements %}
    {% include "requirements/_row.html" %}
  {% endfor %}
  {% endif %}
</ul>
```

(Unchanged besides the empty-state paragraph's class — `_row.html` still
needs `traceability_status` in its rendering context, which both
`create_requirement`'s and `list_requirements`'s template contexts already
pass, per Step 3.)

- [ ] **Step 6: Rewrite `requirements/list.html`**

Replace the full contents of `idea_space/app/templates/requirements/list.html`:

```html
{% extends "base.html" %}
{% block content %}
<div class="page-header">
  <div>
    <div class="page-eyebrow">PRODUCT DEFINITION</div>
    <div class="page-title">Requirements registry</div>
    <div class="page-subtitle">One source of truth from intent to acceptance.</div>
  </div>
  <a class="btn btn-outline" href="/requirements/export.csv">EXPORT CSV</a>
</div>

<div class="metrics-row">
  <div class="metric-card">
    <span class="metric-label">TOTAL</span>
    <span class="metric-value">{{ total_count }}</span>
  </div>
  <div class="metric-card">
    <span class="metric-label">VALIDATED</span>
    <span class="metric-value" style="color: var(--success);">{{ "%02d"|format(validated_count) }}</span>
  </div>
  <div class="metric-card">
    <span class="metric-label">IN REVIEW</span>
    <span class="metric-value" style="color: var(--warning);">{{ "%02d"|format(in_review_count) }}</span>
  </div>
  <div class="metric-card">
    <span class="metric-label">AT RISK</span>
    <span class="metric-value" style="color: var(--danger);">{{ "%02d"|format(at_risk_count) }}</span>
  </div>
</div>

<div class="requirements-layout">
  <div class="requirements-table">
    <div class="panel-toolbar">
      <div class="filter-tabs">
        <a class="filter-tab{% if current_filter == 'all' %} filter-tab--active{% endif %}" href="/requirements?filter=all">ALL {{ total_count }}</a>
        <a class="filter-tab{% if current_filter == 'active' %} filter-tab--active{% endif %}" href="/requirements?filter=active">ACTIVE {{ active_count }}</a>
        <a class="filter-tab{% if current_filter == 'archived' %} filter-tab--active{% endif %}" href="/requirements?filter=archived">ARCHIVED {{ archived_count }}</a>
      </div>
      <span style="font-size:9px; font-weight:700; color: var(--text-muted);">LAST UPDATED</span>
    </div>
    {% include "requirements/_list_only.html" %}
  </div>
  <div class="create-panel">
    <div class="page-eyebrow">NEW REQUIREMENT</div>
    <div style="font-size:20px; font-weight:600;">Define the intent</div>
    <form hx-post="/requirements" hx-target="#requirement-list" hx-swap="outerHTML" style="display:flex; flex-direction:column; gap:16px; margin:0;">
      <div class="field-group">
        <span class="field-label">TITLE</span>
        <input type="text" name="title" class="field-input" placeholder="Describe the user outcome" required>
      </div>
      <div class="field-group">
        <span class="field-label">BUSINESS NEED</span>
        <textarea name="business_need" class="field-input" placeholder="Why this matters now"></textarea>
      </div>
      <div class="field-group">
        <span class="field-label">ACCEPTANCE CRITERIA</span>
        <textarea name="acceptance_criteria" class="field-input" placeholder="What must be true"></textarea>
      </div>
      <select name="status" class="field-input" disabled>
        <option value="draft" selected>Assigned owner: current user</option>
      </select>
      <input type="hidden" name="status" value="draft">
      <button type="submit" class="btn-primary" style="justify-content:center;">CREATE REQUIREMENT</button>
    </form>
  </div>
</div>

<details style="margin-top:26px;">
  <summary style="cursor:pointer; color: var(--text-muted); font-size:11px; font-weight:700;">Manage stakeholders, decisions &amp; risks</summary>
  <div style="margin-top:12px;">
    {% include "stakeholders/_manager.html" %}
    {% include "decisions/_manager.html" %}
    {% include "risks/_manager.html" %}
  </div>
</details>
{% endblock %}
```

The disabled `<select name="status">` plus a hidden `status` input is a
deliberate way to satisfy `create_requirement`'s existing `status: str =
Form("draft")` parameter (the disabled select never actually submits its
value — disabled fields are excluded from form submission — so the hidden
input is what the server sees, always `"draft"`, matching the mockup's
create flow which doesn't expose a status picker either).

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_requirements.py -v`
Expected: PASS

- [ ] **Step 8: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: all tests pass — check any pre-existing requirements test
asserting on `_row.html`'s old markup (e.g. `class="requirement-status"`
text content used to be the raw `requirement.status` string; it's now a
badge showing the computed traceability status instead) and update it.

```bash
git add app/routers/requirements.py app/templates/requirements/ tests/test_requirements.py
git commit -m "feat: add requirements dashboard metrics, filters, CSV export"
```

---

### Task 7: Traceability matrix — computed status, coverage metrics, insights panel

**Files:**
- Modify: `idea_space/app/routers/matrix.py`
- Modify: `idea_space/app/templates/matrix/index.html`
- Test: `idea_space/tests/test_matrix.py`

**Interfaces:**
- Consumes: `traceability_status` (Task 3).

- [ ] **Step 1: Write the failing tests**

Append to `idea_space/tests/test_matrix.py`, matching its existing
`client`/`db_session` fixture convention (already used by
`test_matrix_shows_linked_entities`). Each test gets an isolated
in-memory database per `tests/conftest.py`'s `db_session` fixture, so
`test_matrix_zero_requirements_renders_zero_percent_without_error` can
assert the exact "0%" text, not just "no crash":

```python
def test_matrix_page_shows_coverage_metrics(client):
    response = client.get("/matrix")
    assert response.status_code == 200
    body = response.text
    assert "COVERAGE" in body
    assert "ORPHANED" in body
    assert "VERIFIED" in body


def test_matrix_zero_requirements_renders_zero_percent_without_error(client):
    response = client.get("/matrix")
    assert response.status_code == 200
    assert "0%" in response.text


def test_matrix_link_cell_color_tiers(client, db_session):
    from app.models import Requirement, Stakeholder

    client.post("/stakeholders", data={"name": "Jane", "role": "Sponsor"})
    stakeholder = db_session.query(Stakeholder).filter_by(name="Jane").one()

    client.post("/requirements", data={"title": "Coverage test req"})
    requirement = db_session.query(Requirement).filter_by(title="Coverage test req").one()

    client.post(
        f"/requirements/{requirement.id}/stakeholders",
        data={"stakeholder_id": stakeholder.id},
    )

    response = client.get("/matrix")
    assert response.status_code == 200
    assert "link-badge--partial" in response.text or "link-badge--linked" in response.text
    assert "link-badge--missing" in response.text


def test_matrix_needs_attention_lists_at_risk_before_draft(client, db_session):
    from app.models import Requirement, Risk

    client.post("/requirements", data={"title": "At risk req", "status": "approved"})
    at_risk_requirement = db_session.query(Requirement).filter_by(title="At risk req").one()

    client.post("/risks", data={"title": "Bad vendor", "severity": "high", "status": "open"})
    risk = db_session.query(Risk).filter_by(title="Bad vendor").one()

    client.post(f"/requirements/{at_risk_requirement.id}/risks", data={"risk_id": risk.id})
    client.post("/requirements", data={"title": "Draft req with no links"})

    response = client.get("/matrix")
    assert response.status_code == 200
    body = response.text
    # "At risk req" also appears in the main table, which renders before the
    # attention panel — scope the ordering check to inside the panel itself.
    attention_section = body[body.index("NEEDS ATTENTION"):]
    at_risk_idx = attention_section.index("At risk req")
    draft_idx = attention_section.index("Draft req with no links")
    assert at_risk_idx < draft_idx
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_matrix.py -v`
Expected: FAIL — no metrics markup, no link-badge classes, no attention panel.

- [ ] **Step 3: Rewrite `matrix.py`**

Replace the full contents of `idea_space/app/routers/matrix.py`:

```python
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
```

- [ ] **Step 4: Rewrite `matrix/index.html`**

Replace the full contents of `idea_space/app/templates/matrix/index.html`:

```html
{% extends "base.html" %}
{% block content %}
<div class="page-header">
  <div>
    <div class="page-eyebrow">EVIDENCE MAP</div>
    <div class="page-title">Traceability matrix</div>
    <div class="page-subtitle">See how every requirement connects to delivery and proof.</div>
  </div>
  <a class="btn btn-outline" href="/matrix">SYNC MATRIX</a>
</div>

<div class="metrics-row">
  <div class="metric-card">
    <span class="metric-label">COVERAGE</span>
    <div class="metric-value-row">
      <span class="metric-value" style="color: var(--success);">{{ coverage_pct }}%</span>
    </div>
  </div>
  <div class="metric-card">
    <span class="metric-label">REQUIREMENTS</span>
    <div class="metric-value-row">
      <span class="metric-value">{{ total_count }}</span>
      <span class="metric-note">{{ connected_count }} connected</span>
    </div>
  </div>
  <div class="metric-card">
    <span class="metric-label">ORPHANED</span>
    <div class="metric-value-row">
      <span class="metric-value" style="color: var(--warning);">{{ "%02d"|format(orphaned_count) }}</span>
      <span class="metric-note metric-note--warning">Needs linkage</span>
    </div>
  </div>
  <div class="metric-card">
    <span class="metric-label">VERIFIED</span>
    <div class="metric-value-row">
      <span class="metric-value" style="color: var(--accent);">{{ "%02d"|format(verified_count) }}</span>
      <span class="metric-note">Acceptance passed</span>
    </div>
  </div>
</div>

<div class="matrix-layout">
  {% if not rows %}
  <div class="requirements-table"><p class="agenda-empty" style="padding:20px;">No requirements yet.</p></div>
  {% else %}
  <table class="matrix-table">
    <thead>
      <tr>
        <th>ID</th>
        <th>REQUIREMENT</th>
        <th>TASKS</th>
        <th>DECISIONS</th>
        <th>RISKS</th>
        <th>STAKEHOLDERS</th>
        <th>STATUS</th>
      </tr>
    </thead>
    <tbody>
      {% for row in rows %}
      <tr>
        <td style="color: var(--accent); font-weight:700;">REQ-{{ "%03d"|format(row.requirement.id) }}</td>
        <td><a href="/requirements/{{ row.requirement.id }}" style="text-decoration:none;">{{ row.requirement.title }}</a></td>
        <td><span class="link-badge link-badge--{{ row.task_tier }}">{{ row.requirement.tasks|length }}</span></td>
        <td><span class="link-badge link-badge--{{ row.decision_tier }}">{{ row.requirement.decisions|length }}</span></td>
        <td><span class="link-badge link-badge--{{ row.risk_tier }}">{{ row.requirement.risks|length }}</span></td>
        <td><span class="link-badge link-badge--{{ row.stakeholder_tier }}">{{ row.requirement.stakeholders|length }}</span></td>
        <td>
          {% if row.status == "at_risk" %}
          <span class="status-badge status-badge--danger">AT RISK</span>
          {% elif row.status == "verified" %}
          <span class="status-badge status-badge--success">VERIFIED</span>
          {% elif row.status == "partial" %}
          <span class="status-badge status-badge--warning">PARTIAL</span>
          {% else %}
          <span class="status-badge status-badge--neutral">DRAFT</span>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
  <div class="coverage-panel">
    <div class="page-eyebrow">COVERAGE SIGNAL</div>
    <div style="font-size:20px; font-weight:600;">Close the final gaps</div>
    <div class="coverage-ring-area">
      <div class="coverage-ring" style="--pct: {{ coverage_pct }};"></div>
      <div class="coverage-ring-value">{{ coverage_pct }}% COVERED</div>
    </div>
    <div style="font-size:8px; font-weight:700; color: var(--text-muted);">NEEDS ATTENTION</div>
    {% if not needs_attention %}
    <p class="agenda-empty">Nothing needs attention.</p>
    {% endif %}
    {% for item in needs_attention %}
    <div class="attention-item">
      <span class="attention-dot" style="background: {{ 'var(--danger)' if item.status == 'at_risk' else 'var(--warning)' }};"></span>
      <div class="attention-detail">
        <span class="attention-id" style="color: {{ 'var(--danger)' if item.status == 'at_risk' else 'var(--warning)' }};">REQ-{{ "%03d"|format(item.requirement.id) }}</span>
        <span class="attention-text">{{ item.reason }}</span>
      </div>
    </div>
    {% endfor %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Update the two pre-existing matrix tests**

The redesigned matrix table renders numeric link-count badges per cell
instead of comma-joined entity names, and empty cells are now
`link-badge--missing` badges showing `0`, not `<span class="matrix-empty">`.
Both pre-existing tests in `idea_space/tests/test_matrix.py` assert on the
old shape and must be updated to match the new one:

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
    # The redesigned matrix shows per-category link COUNTS, not names — one
    # linked item per category renders as a "partial"-tier badge (0 would be
    # "missing", 2+ would be "linked").
    assert "Req with links" in body
    assert body.count("link-badge--partial") == 4
    assert "link-badge--missing" not in body


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
    assert response.content.count(b"link-badge--missing") == 4
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_matrix.py -v`
Expected: PASS

- [ ] **Step 7: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: all tests pass.

```bash
git add app/routers/matrix.py app/templates/matrix/index.html tests/test_matrix.py
git commit -m "feat: add matrix coverage metrics, per-cell tiers, needs-attention panel"
```

---

### Task 8: Manual whole-app browser verification

**Files:** none (verification only, may produce small fix commits if issues are found)

- [ ] **Step 1: Start the app**

```bash
cd idea_space && rm -f idea_space.db && python -m uvicorn app.main:app --port 8420 &
curl -s http://127.0.0.1:8420/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 2: Seed a realistic dataset via curl**

Create 2-3 tasks with varied due dates (today, tomorrow, next week),
complete one, create 2 stakeholders/decisions/risks (one high-severity open
risk), create 3-4 requirements with varied links (one fully linked +
approved for VERIFIED, one with a linked high-severity open risk for AT
RISK, one with no links for DRAFT), matching the fixture shapes already
used in Slice 3a's manual verification.

- [ ] **Step 3: Visually verify each of the 4 pages in a real browser**

Using the browser automation tools (not curl): open `/tasks` and confirm
the metrics row, quick capture, and NOW/NEXT/DONE columns render with the
dark theme and no layout breakage; open `/calendar` and check MONTH view
renders a full grid, switching to WEEK and AGENDA both work, and dragging
a task onto a different day reschedules it without a full-page dump into
the fragment (confirm via a follow-up screenshot that only the calendar
area updates); open `/requirements` and confirm metrics, filter tabs, the
create panel, and CSV export (download and check content) all work; open
`/matrix` and confirm the coverage ring, per-cell color tiers, and needs-
attention panel render correctly for the seeded AT RISK/VERIFIED/DRAFT mix.

- [ ] **Step 4: Fix anything found, then stop the server**

If a visual or functional defect is found, fix it directly (small,
targeted commit — this mirrors Slice 1/2/3a's Task 8 pattern, where manual
verification has caught real bugs per-slice that automated tests missed).

```bash
kill %1  # or find and kill the uvicorn process by port
rm -f idea_space.db
```

## Self-Review Notes

- **Spec coverage:** every Goals bullet has a task (shell/tokens: Task 2;
  Tasks board: Task 4; Calendar: Task 5; Requirements: Task 6; Matrix:
  Task 7); every Data Model Changes item has Task 1; the shared
  `_traceability_status` helper from the spec's Architecture section is
  Task 3, consumed by both Task 6 and Task 7 exactly as specified; every
  Testing bullet in the spec has a corresponding test in this plan.
- **Fixed during self-review:** Task 4 originally had `reschedule_task`
  call `calendar_router.render_calendar` (the full-page renderer) — caught
  and corrected in Task 5 to call `_render_calendar_fragment` instead,
  which is exactly the latent full-page-into-innerHTML bug the spec calls
  out fixing; Task 5's `_month.html` draft step included a dead/broken
  prev-month expression, removed in the same step rather than left in;
  Task 5's `_build_month_context` had a redundant, confusing two-part
  days-in-grid calculation, replaced with a single clear loop; `render_calendar`
  and `_render_calendar_fragment` duplicated their whole view-dispatch
  block, extracted into a shared `_view_context_and_template` helper.
- **Fixed after reading the actual codebase (not just the spec):** every
  test block in this plan originally assumed a module-level
  `client = TestClient(app)` and direct `app.db.SessionLocal()` use —
  reading `tests/conftest.py` and the existing test files showed this
  codebase instead uses `client`/`db_session` pytest fixtures (a fresh
  in-memory SQLite DB per test) everywhere; every test in every task was
  rewritten to match. Task 4's board rewrite also originally dropped the
  pre-existing `GET /tasks?labels=X` filter (tested by
  `test_filter_tasks_by_label`/`test_filter_tasks_by_multiple_labels_is_or_matched`
  in `test_tasks.py`) since the board only rendered all open/done tasks —
  fixed by threading `label_ids` through `_task_metrics`/`_render_task_board`
  and adding a label filter nav to `_board.html`, plus a regression test.
  Three more pre-existing tests were found to assert on markup these tasks
  remove: `test_navigation.py`'s `class="main-nav"` check (Task 2 renames
  it to `.primary-nav`) and `test_matrix.py`'s two tests asserting on
  comma-joined entity names and a `matrix-empty` count (Task 7 replaces
  both with numeric `link-badge` counts) — all three now have explicit
  replacement code in their task's steps instead of a vague "check and
  update" note. `test_calendar.py` already existed with 4 tests relying on
  `/calendar?start=...` defaulting to week view — Task 5 explicitly updates
  them to pass `view=week` now that month is the default.
- **Type/name consistency:** `_render_task_board` (Task 4), `render_calendar`
  / `_render_calendar_fragment` (Task 5, consumed by Task 4), and
  `traceability_status` (Task 3, consumed by Tasks 6-7) are used with the
  same names and signatures everywhere they're referenced across tasks.
