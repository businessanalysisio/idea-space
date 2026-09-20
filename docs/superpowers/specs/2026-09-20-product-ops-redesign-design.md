# Idea Space — Product Ops Redesign — Design Spec

**Date:** 2026-09-20
**Status:** Approved for implementation planning

## Context

Slices 1-3a shipped the functional core of Idea Space (tasks, calendar, labels,
reminders, activity history, completion notes, archiving, and the BA
traceability foundation: Requirements/Stakeholders/Decisions/Risks/Matrix),
styled with the SOL design system from Slice 2.

The user supplied a complete visual mockup (a "Product Ops" dark theme: purple
accent, sidebar navigation, dashboard-style stat cards) covering four screens:
Tasks, Calendar, Requirements, and Traceability. This spec covers rebuilding
the app to match that mockup, including the behavior it implies (a NOW/NEXT/
DONE task board, a month-view calendar, and computed coverage/status signals
on the matrix) — not just a visual reskin.

This is a redesign of existing screens, not a new JTBD slice. No new business
entities are introduced.

## Goals

- Replace the SOL design tokens with the new dark "Product Ops" theme
  (colors, typography, spacing) across the whole app.
- Replace the top-header layout with a fixed sidebar (brand, nav, status
  card) + top bar (breadcrumb, decorative search, avatar).
- Tasks: dashboard header, 4 metric cards (Open/In Focus/Completed/Blocked),
  a quick-capture bar, and a 3-column NOW/NEXT/DONE board — all derived from
  existing task data plus one new `blocked` flag.
- Calendar: add a real month-grid view (new) alongside the existing week
  view (restyled) and a new agenda view, with a MONTH/WEEK/AGENDA toggle.
- Requirements: dashboard header, 4 metric cards (Total/Validated/In
  Review/At Risk), a table with filter tabs and sort, and a redesigned
  create-requirement side panel.
- Traceability: dashboard header, 4 metric cards (Coverage %/Requirements/
  Orphaned/Verified), a matrix table with per-cell link-count badges and a
  computed per-row status badge, and a "needs attention" insights panel.

## Non-Goals

- **No new "Test"/verification entity.** The mockup's matrix has a TESTS
  column; the app has no such entity and adding one is a new CRUD subsystem,
  not a redesign. The matrix keeps its existing 4th column, **Stakeholders**
  (what the app actually tracks), instead of Tests.
- **No real search.** The sidebar/top-bar search box and ⌘K hint are
  decorative markup only — no search endpoint, no results dropdown.
- **No multi-user owner picker.** Only one seeded user exists until Slice 4
  (Multi-User & Multi-Device). The "Assign owner" control shows the current
  user as a fixed, disabled selection rather than a real picker.
- **No new WebSocket/live-sync.** The matrix's "SYNC MATRIX" control is a
  plain link back to `/matrix` (data is already live on every request).

## Data Model Changes

- `Task.blocked: bool`, default `False`. Toggled by the user on a task card;
  feeds the BLOCKED metric. New column on an existing table — needs a
  migration (see below).
- `Requirement.updated_at: DateTime(timezone=True)`, default `_utcnow` at
  creation, **and set to `_utcnow()` on every `PATCH /requirements/{id}`**
  (title/description/business_need/acceptance_criteria/status edit). Powers
  the "Updated N ago" row metadata and the LAST UPDATED sort. New column on
  an existing table — needs a migration.
- Migration: extend the existing hand-rolled `ensure_completion_note_column`
  pattern in `app/main.py`'s startup (idempotent `ALTER TABLE ... ADD COLUMN`
  guarded by a `PRAGMA table_info` check) to also ensure `tasks.blocked`
  (`BOOLEAN DEFAULT 0`) and `requirements.updated_at` (`DATETIME`, backfilled
  from `created_at` for existing rows) exist. Same convention as Slice 2,
  same reasoning: no Alembic in this codebase yet.

## Design Tokens

Replace the SOL `:root` custom properties in `app/static/app.css` with:

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
}
```

Every existing component class in `app.css` is redefined against these
tokens (no component keeps a SOL-era hardcoded hex value). `Inter` is loaded
from Google Fonts in `base.html`'s `<head>`, matching the mockup.

## Architecture

### Base layout (`app/templates/base.html`)

Replace the `<header class="app-header">` with:

```
<div class="app-shell">
  <aside class="app-sidebar">
    <div class="brand">...</div>
    <nav class="primary-nav">
      <a class="nav-item{active}" href="/tasks">Tasks</a>
      <a class="nav-item{active}" href="/calendar">Calendar</a>
      <a class="nav-item{active}" href="/requirements">Requirements</a>
      <a class="nav-item{active}" href="/matrix">Traceability</a>
    </nav>
    <div class="sidebar-spacer"></div>
    <div class="workspace-status">...static "All systems focused"...</div>
  </aside>
  <div class="app-body">
    <div class="topbar">
      <div class="breadcrumb">WORKSPACE / {% block breadcrumb %}{% endblock %}</div>
      <div class="topbar-actions">...decorative search...avatar...</div>
    </div>
    <div hx-get="/reminders/due" hx-trigger="load" hx-swap="outerHTML" id="reminder-banner"></div>
    <main>{% block content %}{% endblock %}</main>
  </div>
</div>
```

The active nav item is set per-page by each template overriding a
`{% block active_nav %}` value compared against a `current_nav` context
variable each router already has reason to pass (or, simpler and consistent
with the existing convention of full-page links with no client routing:
each router passes `active_nav="tasks"|"calendar"|"requirements"|"matrix"`
in its template context, and `base.html` compares it against each nav
item's own key). The breadcrumb block is set the same way, one word per
page (TASKS / CALENDAR / REQUIREMENTS / TRACEABILITY).

`app.js` and the reminder banner behavior are unchanged.

### Tasks (`app/routers/tasks.py`, `app/templates/tasks/`)

- `list_tasks` (`GET /tasks`) computes and passes: `open_count`,
  `in_focus_count` (open tasks with `due_date` inside "today" in UTC —
  reuse the existing overdue-flag date math), `completed_count`,
  `velocity` (`round(completed_count / (completed_count + open_count) * 100)`,
  0 when both are 0), `blocked_count` (`Task.blocked == True`, any status).
- Board columns are **derived, not stored**: NOW = open & (`due_date` is
  today or in the past); NEXT = open & `due_date` is in the future; DONE =
  status `done`, ordered by `completed_at` desc, limited to the 10 most
  recent. This applies only to the default view (no `status` query param,
  or `status=open`); `?status=archived` keeps the existing plain list view
  (restyled as cards, no columns), reached via a small "View archived" link
  in the page header rather than the old three-way status nav.
- New endpoint `PATCH /tasks/{id}/block` toggles `blocked` (flip current
  value, idempotent by construction), re-renders the full board fragment.
- The board (metrics + quick-capture + 3 columns), the archived list, and
  the label filter bar are wrapped in one single-root fragment
  `<div id="task-board">...</div>` used as the `hx-target`/`hx-swap=outerHTML`
  for create/complete/block/label-filter actions, matching the Global
  Constraint on htmx fragment safety.
- Quick-capture bar is a `<form>` posting to the existing `POST /tasks`
  with just a `title` input; `due_date` is defaulted to "today" via a
  hidden field populated by a small inline script (`new Date().toISOString().slice(0,10)`),
  since `create_task` already requires `due_date`. The existing full task
  form (all fields) opens from the "NEW TASK" button (a `<details>`/toggle
  disclosure, no new JS framework needed).

### Calendar (`app/routers/calendar.py`, `app/templates/calendar/`)

- `GET /calendar` gains a `view: str = "month"` query param
  (`"month" | "week" | "agenda"`, 400 on anything else) alongside the
  existing `start` param (used by week) and a new `month: str | None`
  param (`YYYY-MM`, used by month; defaults to the current month).
- Three new/changed templates, each a single-root fragment used both for
  the full page and for the reschedule response:
  - `calendar/_month.html` — root `<div id="calendar-content" data-view="month" data-month="{{ month_str }}">`.
    Computes a Monday-start grid padded to full weeks covering the month.
    Each day cell keeps the existing `class="calendar-day" data-date="..."`
    contract so drag-reschedule keeps working unchanged in month view.
  - `calendar/_week.html` — the existing week markup, restyled, root
    `<div id="calendar-content" data-view="week" data-week-start="{{ week_start_str }}">`.
  - `calendar/_agenda.html` — root `<div id="calendar-content" data-view="agenda">`,
    a flat chronological list (no day boxes) of open tasks (real +
    recurrence-projected virtual occurrences, reusing the existing
    `project_occurrences` call) due in the next 14 days.
  - `calendar/index.html` (extends base) includes the right fragment by
    `view`, plus the always-present "Upcoming Agenda" side panel (next
    calendar day, real or virtual, that has ≥1 item — reusing the same
    day-items computation already used for week view) and the
    MONTH/WEEK/AGENDA toggle (plain links to `/calendar?view=...`).
- `PATCH /tasks/{id}/reschedule` gains `view: str = Form("month")`,
  `month: str | None = Form(None)`, `start: str | None = Form(None)` and
  dispatches to whichever of the three render helpers matches `view`,
  returning **only that fragment** (not a full page). `app.js`'s drop
  handler is updated to read `view`/`data-month`/`data-week-start` off
  `#calendar-content`, include them in the PATCH body, and replace
  `#calendar-content`'s `outerHTML` (not `main.innerHTML`) with the
  response — this also fixes a latent bug where the old handler dumped a
  full HTML document string into `main.innerHTML`.

### Shared: computed traceability status

Both the Requirements list and the Traceability matrix badge every
requirement with the same underlying state, computed by one helper,
`_traceability_status(requirement) -> Literal["at_risk", "verified", "partial", "draft"]`,
added to `app/services/traceability.py` and imported by both
`requirements.py` and `matrix.py` (no duplicated logic). Checked in this
order:

1. **`at_risk`** — any linked `Risk` with `severity == "high"` and
   `status == "open"`.
2. **`verified`** — `requirement.status` in `{"approved", "delivered"}`
   **and** at least one link in every one of Stakeholders/Decisions/Tasks
   (Non-Goals: no Tests category).
3. **`partial`** — at least one link in any category (regardless of
   `requirement.status`), doesn't meet `verified`, isn't `at_risk`.
4. **`draft`** — zero links in every category.

Each page maps the same 4 values to its own badge text: the Requirements
list shows AT RISK/VALIDATED/PARTIAL/DRAFT; the matrix shows AT
RISK/VERIFIED/PARTIAL/DRAFT — same computation, different label per the
mockup's own wording on each screen.

### Requirements (`app/routers/requirements.py`, `app/templates/requirements/`)

- `list_requirements` (`GET /requirements`) gains a `filter: str = "all"`
  query param (`"all" | "active" | "archived"`, 400 on anything else;
  active = `status != "delivered"`, archived = `status == "delivered"`).
  The 4 metric cards (`total_count`, `validated_count`, `in_review_count`,
  `at_risk_count`) are always computed over **every** requirement in the
  workspace via `_traceability_status`, independent of `filter` — they sum
  to the true total, matching the mockup (8 validated + 3 in review + 1 at
  risk = 12 total). `filter` only changes which rows the table itself
  shows (and the ALL/ACTIVE/ARCHIVED tab counts, which are separate small
  counts next to each tab). `in_review_count` counts `requirement.status
  == "in_progress"` (independent of traceability status). Requirements are
  ordered by `updated_at` desc (LAST UPDATED sort; the mockup's sort
  control is decorative-only otherwise — no other sort order is
  implemented).
- Row shows: ID (`REQ-{id:03d}`), title, "Updated {relative time} ago"
  (from `updated_at`), owner name (the single seeded user), the
  `_traceability_status` badge (AT RISK/VALIDATED/PARTIAL/DRAFT), and a
  links count (`len(stakeholders) + len(decisions) + len(risks) +
  len(tasks)`).
- New `GET /requirements/export.csv` streams a CSV (columns: id, title,
  status, owner, updated_at, links_count) of all requirements — the
  mockup's "EXPORT CSV" button is real, not decorative, since it's a small,
  well-bounded addition using data already on hand.
- The create-requirement side panel keeps the existing 4 fields (title,
  business need, acceptance criteria — description is dropped from the
  visible form to match the mockup's 3-field layout but stays writable via
  PATCH on the detail page) plus the disabled single-option owner select
  (Non-Goals).
- `edit_requirement`/`create_requirement` set `requirement.updated_at =
  datetime.now(timezone.utc)` on every successful write.

### Traceability matrix (`app/routers/matrix.py`, `app/templates/matrix/`)

- Per-requirement status badge uses `_traceability_status` (see above),
  displayed as AT RISK/VERIFIED/PARTIAL/DRAFT.
- Per-cell link-count badge color (Tasks/Decisions/Risks/Stakeholders
  columns): 0 → danger ("missing"), 1 → warning ("partial"), ≥2 → success
  ("linked") — matches the mockup's LINKED/PARTIAL/MISSING legend.
- Metrics: `coverage_pct` = round(requirements with ≥1 link of any kind /
  total * 100) (0 when there are no requirements); `connected_count` =
  that same numerator; `orphaned_count` = requirements with zero links in
  every category; `verified_count` = requirements whose computed status is
  VERIFIED.
- "Needs attention" side panel: up to 5 requirements whose computed status
  is AT RISK or DRAFT (AT RISK first, then DRAFT, each in `updated_at`
  desc order), each with a one-line reason: AT RISK → "Missing risk
  mitigation" style text naming the open high-severity risk's title
  truncated to 40 chars; DRAFT → "No links yet".
- The coverage ring is a pure-CSS `conic-gradient` circle sized by
  `coverage_pct` (inline `style="--pct: {{ coverage_pct }}"` consumed by a
  CSS rule) — no chart library, no SVG path math.
- "SYNC MATRIX" is `<a href="/matrix">` (a plain reload link — data is
  already live).

## Key Flows

1. **View the tasks board:** `GET /tasks` renders the dashboard header,
   4 metrics, quick-capture bar, and the NOW/NEXT/DONE board computed from
   current data. Completing, creating, blocking, or filtering by label
   re-renders the single `#task-board` fragment.
2. **View the calendar:** `GET /calendar` defaults to the month grid for
   the current month; the toggle switches to week or agenda via a normal
   link (full page reload, consistent with how status filters already work
   elsewhere in the app). Dragging a task onto a day (month or week view)
   reschedules it in place via the updated `#calendar-content` swap.
3. **View requirements:** `GET /requirements` renders the dashboard header,
   4 metrics, filter tabs, the sorted table, and the create panel. Creating
   a requirement re-renders the list; editing/deleting updates
   `updated_at` and the computed status shown on both the requirements list
   and the matrix.
4. **View the traceability matrix:** `GET /matrix` renders the dashboard
   header, 4 metrics, the per-cell-colored table, and the "needs attention"
   panel, using the same computed-status helper the requirements list uses.

## Error Handling & Edge Cases

- `GET /calendar` with an invalid `view` value → `400`.
- `GET /requirements` with an invalid `filter` value → `400`.
- Zero requirements: matrix and requirements metrics all render as 0/0%
  rather than dividing by zero (explicit guard in the computation helper).
- A month with no tasks due: month grid renders normally, all day cells
  empty, "Upcoming Agenda" panel shows an explicit empty state ("Nothing
  scheduled") instead of a blank card.
- `PATCH /tasks/{id}/block` on an unknown or archived task → `404`
  (matches the existing `reschedule`/`complete` 404 convention: task must
  exist; unlike reschedule, blocking is allowed on any status except
  archived, since a done task showing "blocked" would be meaningless —
  archived tasks return 404).
- The hand-rolled migration helper is idempotent: re-running startup
  against a database that already has `tasks.blocked` or
  `requirements.updated_at` is a no-op (same `PRAGMA table_info` guard
  pattern as `ensure_completion_note_column`).

## Testing

- Migration test: a legacy DB (created via raw DDL without the two new
  columns, matching the existing `ensure_completion_note_column` test
  pattern) gets both columns added on startup, and `requirements.updated_at`
  is backfilled from `created_at` for pre-existing rows.
- Task board: NOW/NEXT/DONE derivation tests (a task due today, a task due
  tomorrow, a done task each land in the right column); metrics tests
  (open/in-focus/completed/velocity/blocked counts against a known
  fixture); `PATCH /tasks/{id}/block` toggles and is idempotent-safe on
  repeated calls (flips each time — verify two calls return to original
  state); 404 on blocking an archived or nonexistent task.
- Calendar: month-grid test (correct day count/padding for a known month,
  e.g. a month starting on a Sunday needing 6 rows); `view=agenda` returns
  only items in the next 14 days; invalid `view` → 400; reschedule via
  each of the three views returns the matching fragment shape (root
  `data-view` attribute matches what was requested).
- Requirements: computed-status tests for all 4 states (AT RISK via a
  linked open high-severity risk overriding an `approved` status; VERIFIED
  requiring all 3 categories linked; PARTIAL; DRAFT); `updated_at` changes
  on edit and not on read; `filter=active/archived` partition tests;
  invalid `filter` → 400; CSV export returns the right row count and a
  parseable CSV (header + one row per requirement).
- Matrix: per-cell color-tier tests (0/1/≥2 counts map to
  missing/partial/linked); coverage/orphaned/verified metric tests against
  a fixture with a known mix of link states; zero-requirements case
  renders 0% without a division error; "needs attention" panel ordering
  (AT RISK before DRAFT) and the 5-item cap.
- Manual browser verification of all four redesigned pages against the
  mockup (layout, dark theme tokens, drag-reschedule across month/week,
  quick-capture, block toggle, CSV export download), per the pattern
  established in Slices 1-3a.

## Roadmap After This Redesign

This redesign does not change the JTBD roadmap. After it lands, "keep
going" resumes at Slice 3b (Close Traceability Gaps), unchanged from the
plan in `docs/superpowers/specs/2026-09-20-ba-traceability-foundation-design.md`.
