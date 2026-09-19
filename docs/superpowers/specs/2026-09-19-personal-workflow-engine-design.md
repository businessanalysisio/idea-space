# Idea Space — Personal Workflow & Commitment Engine (Slice 1) — Design Spec

**Date:** 2026-09-19
**Status:** Approved for implementation planning

## Context

Idea Space is a local-first Business Analyst project workspace whose primary
job is: *"When I need to prove that analysis is complete, I want to trace
every requirement from business need through delivery, so I can reduce
omissions and rework."*

The full product backlog spans four largely independent sub-projects:

1. **Personal Workflow & Commitment Engine** — recurring tasks, calendar
   planning, labels/filtering, reminders. *(this slice)*
2. **Confidence, History & Follow-Through** — activity/audit log, completion
   notes. *(next slice — reminders were pulled forward into slice 1)*
3. **BA Traceability Workspace** — requirements, stakeholders, decisions,
   risks, traceability matrix, gap detection, impact analysis, project
   summary reports. *(the product's stated primary job)*
4. **Multi-User & Multi-Device** — shared workspaces (including a general
   shared file area, not just per-record attachments), cross-device sync,
   auth, conflict resolution.

This spec covers **Slice 1** only. Slices 2–4 are out of scope here but the
data model is deliberately shaped to avoid rework when they land (see
"Future-proofing" below).

## Goals (Slice 1)

Deliver the JTBDs that reduce time-to-capture, time-to-decide, and
forgetting-anxiety for personal commitments:

- **Recurring Tasks** — a responsibility reappears automatically at the
  right interval without manual recreation.
- **Calendar Planning** — see tasks against specific dates; move them in
  under 3 actions; overdue tasks stay visible.
- **Task Organization, Labels & Filtering** — group/filter by label and
  status without losing list state.
- **Reminders** — a nudge at a useful time, with snooze/dismiss, suppressed
  once a task is done/archived.

Explicitly out of scope for this slice: audit history / completion notes
(slice 2), any BA entity (requirement/stakeholder/decision/risk, slice 3),
and anything multi-user (accounts, sharing, sync, slice 4).

## Platform & Stack

- **Platform:** local web app — a local server the user's browser talks to
  (not a pure browser-only app, and not a packaged desktop binary). Chosen
  because it's easiest to extend into slice 4 (multi-user/sync) later,
  since the app is already server-based.
- **Backend:** Python, FastAPI, SQLite.
- **Frontend:** server-rendered Jinja2 templates + htmx for partial updates.
  No SPA framework. Drag-and-drop uses the native HTML5 drag/drop JS API
  only to capture the gesture; the drop handler fires an htmx-style request
  to persist the change.

## Architecture

```
idea_space/
  app/
    main.py              # FastAPI app, router mounting
    db.py                # SQLite engine/session
    models.py            # SQLAlchemy models
    routers/
      tasks.py           # create/complete/reschedule/delete
      calendar.py        # day/week views
      labels.py          # CRUD + filtering
      reminders.py       # due-reminder polling, snooze/dismiss
    services/
      recurrence.py      # next-occurrence calc + virtual projection
    templates/
      base.html, task_list.html, calendar_week.html, calendar_day.html, ...
  tests/
```

## Data Model

- `workspace(id, name)` and `user(id, workspace_id, name)` — single default
  row each, seeded on first run. This is the "future-proofing" hook: slice 4
  doesn't need to retrofit ownership/workspace scoping onto existing rows.
- `task(id, workspace_id, owner_id, title, description, status[open|done],
  due_date, recurrence_series_id nullable, recurrence_pattern,
  recurrence_interval, recurrence_days_of_week, recurrence_active,
  created_at, completed_at)`
- `label(id, workspace_id, name, color)` and `task_label(task_id, label_id)`
  join table.
- `reminder(id, task_id, remind_at, dismissed_at, snoozed_until)`.

Recurrence is stored **inline on the task row**, not a separate template
table. Completing a task with `recurrence_active=true` creates a **new**
task row carrying the same `recurrence_series_id` and recurrence config,
with `due_date` advanced by the rule. Completed rows are never mutated
again — this is what satisfies "pause/stop recurrence without deleting task
history."

## Key Flows

- **Create recurring task**: form submit → `POST /tasks` creates a row with
  pattern/interval/start date; `recurrence_series_id` defaults to its own id.
- **Calendar view**: `GET /calendar?view=week&date=...` returns real task
  rows due in range **plus** virtual (non-persisted) projected occurrences
  computed from each active recurring task's rule, for dates beyond its
  current instance. Virtual occurrences render visually distinct and are
  not draggable or completable — they're a preview, not yet real.
- **Drag to reschedule**: drop handler fires `PATCH /tasks/{id}/reschedule`
  with the new date → server updates `due_date`, returns the updated
  calendar partial for htmx to swap in. Only real instances are valid drop
  targets.
- **Complete task**: `POST /tasks/{id}/complete` sets `status=done`,
  `completed_at=now`; if `recurrence_active`, computes the next `due_date`
  via `services/recurrence.py` and inserts the successor row (same series
  id, `status=open`).
- **Pause/stop recurrence**: `PATCH /tasks/{id}/recurrence {active: false}`
  on the current open instance — its own completion won't spawn a
  successor. There's no separate pause-vs-stop state; both flip this flag,
  reversible until the instance is completed.
- **Labels/filtering**: label CRUD; task list accepts
  `?labels=1,2&status=open`, OR-matching across selected labels, with a
  clear-all control. Filter state lives in the URL query string so it
  round-trips without extra client-side state.
- **Reminders**: `remind_at` set per task; frontend polls
  `GET /reminders/due` every 30s via `hx-trigger`, rendering a
  dismiss/snooze banner. The query excludes tasks with `status != open`,
  which satisfies "completed/archived tasks suppress future reminders."

## Error Handling & Edge Cases

- A recurrence rule that can't produce a next date (e.g. a custom pattern
  past its end condition) → completion succeeds, no successor row is
  created; behaves like a natural stop.
- Deleting a label removes only its `task_label` join rows — tasks
  themselves are untouched.
- Single local user for this slice, so no concurrency/locking concerns
  beyond SQLite's own write-serialization.
- Times are stored in UTC and converted to browser-local time for display —
  this keeps timezone handling correct without rework when slice 4
  (multi-device) lands.

## Testing

- Backend: pytest + FastAPI `TestClient` against a temp SQLite file.
  Table-driven unit tests for `recurrence.py` (daily/weekly/monthly/custom
  next-date calculation), integration tests for complete→spawn-next,
  label filter queries, and the due-reminder query.
- Drag-and-drop and the polling banner are hard to meaningfully unit-test;
  covered by manual browser verification for this slice rather than
  introducing e2e tooling. Revisit if/when the app grows enough to justify
  Playwright coverage.

## Roadmap After This Slice

1. ~~Slice 1: Personal Workflow & Commitment Engine~~ *(this spec)*
2. Slice 2: Confidence, History & Follow-Through — audit log, completion
   notes (layers onto the `task` table's lifecycle).
3. Slice 3: BA Traceability Workspace — requirements, stakeholders,
   decisions, risks, traceability matrix, gap detection, impact analysis,
   project summary reports.
4. Slice 4: Multi-User & Multi-Device — auth, real multi-user workspaces,
   a general shared file area, cross-device sync, conflict resolution.
