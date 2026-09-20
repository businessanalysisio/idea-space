# Idea Space — Confidence, History & Follow-Through (Slice 2) — Design Spec

**Date:** 2026-09-20
**Status:** Approved for implementation planning

## Context

Slice 1 (Personal Workflow & Commitment Engine) shipped recurring tasks,
calendar planning, labels/filtering, and reminders. This spec covers
**Slice 2** per the roadmap in
`docs/superpowers/specs/2026-09-19-personal-workflow-engine-design.md`:
audit history and completion notes, plus a visual restyle of the whole
app using the SOL design system (`docs/superpowers/DESIGN.md`), which
did not exist when Slice 1 shipped its bare-HTML UI.

## Goals (Slice 2)

- **Activity History**: an audit log recording status and due-date
  changes on a task, viewable after the fact.
- **Completion Notes**: an optional note attachable when completing a
  task, to record what was accomplished.
- **Archiving**: a real third task status (`open` | `done` | `archived`)
  so completed work can be moved out of the default views while its
  history remains fully accessible. Only `done` tasks can be archived,
  manually, via an explicit action — no automatic/scheduled archiving in
  this slice.
- **Visual restyle**: apply the SOL design system consistently across
  the entire app (Slice 1's UI included), since a partial restyle would
  look inconsistent.

Explicitly out of scope: ownership-change tracking has no trigger in this
slice (the app remains single-user until Slice 4), ownership reassignment
UI, automatic/scheduled archiving, and any change to the recurrence,
calendar, or reminder *behavior* established in Slice 1 (only their
visual presentation changes).

## Data Model

- `Task` gains:
  - `completion_note: str | None` (nullable `Text`) — set only when
    completing a task; a recurring task's successor does **not** inherit
    it, since it belongs to that specific occurrence.
  - `status` now allows `"open" | "done" | "archived"` (previously
    `"open" | "done"` only).
- New `ActivityLog` model:
  `id, workspace_id, task_id, field_name, old_value, new_value, changed_at`.
  Generic by design (`field_name` is a string, `old_value`/`new_value`
  are strings) so it can cover any tracked field without a schema
  migration — but only `"status"` and `"due_date"` are actually written
  in this slice. `workspace_id` is denormalized onto the log row rather
  than requiring a join through `task_id`, matching the future-proofing
  convention established in Slice 1.

## Architecture

- New `app/services/activity.py`:
  `record_change(db: Session, task: Task, field_name: str, old_value: str | None, new_value: str) -> None`
  — constructs an `ActivityLog` row and adds it to the session (does not
  commit; callers commit alongside their own state change). Called
  explicitly from each mutating endpoint that touches a tracked field —
  no SQLAlchemy event hooks, matching the codebase's existing explicit
  style and keeping the three call sites easy to trace and test.
- `app/routers/tasks.py` additions:
  - `POST /tasks/{task_id}/archive` — 404 unless the task exists and
    `status == "done"`. Sets `status = "archived"`, calls
    `record_change(db, task, "status", "done", "archived")`. The
    triggering form carries hidden `status`/`labels` fields mirroring
    the currently-viewed filter, so the response re-renders the correct
    filtered `_task_list_only.html` (the archived task disappears from
    whatever list it was archived from).
  - `GET /tasks/{task_id}/history` — 404 for an unknown task; otherwise
    returns an htmx fragment listing that task's `ActivityLog` entries
    (newest first) plus its `completion_note` if present. Toggled inline
    per row via a "History" link.
  - `complete_task` gains an optional `completion_note: str | None = Form(None)`
    field; sets it on the task and calls
    `record_change(db, task, "status", "open", "done")`.
  - `reschedule_task` calls
    `record_change(db, task, "due_date", <old date string>, <new date string>)`
    before applying the date change.
  - `list_tasks` validates `status` against `{"open", "done", "archived"}`
    and returns `400` for anything else, instead of silently returning
    an empty list (closing a gap flagged in Slice 1's final review).
  - `list_tasks`'s response also carries nav links for Open / Done /
    Archived, so Slice 1's status-filtering capability (built in Task 10
    but never linked from any page) and the new Archived view are both
    actually reachable in the browser.

## Data Flow

1. **Complete with a note**: user optionally types into an inline text
   input next to the Done button; `POST /tasks/{id}/complete` receives
   `completion_note` alongside the existing fields, stores it, and logs
   the status change.
2. **Reschedule**: dragging a task to a new day (existing Slice 1 flow)
   now also writes an `ActivityLog` row recording the due-date change,
   with no visible change to the drag interaction itself.
3. **Archive**: from the Done view, clicking "Archive" on a task moves
   it to `archived` and logs the status change; it no longer appears in
   the Open or Done views, only in the Archived view.
4. **View history**: clicking "History" on any task row (open, done, or
   archived) fetches and inline-expands its audit trail and completion
   note, if any.

## Error Handling & Edge Cases

- Archiving a task that is not `done` (including an already-archived
  task) → `404`, same convention as `reschedule_task`'s existing
  status check.
- An invalid `?status=` value on `GET /tasks` → `400`.
- A task with no activity yet (never rescheduled, still open) shows an
  empty history with just its creation — no log entries are backfilled
  for the create event itself in this slice; history starts accumulating
  from the first tracked change.
- Completing without a note leaves `completion_note` as `None` (no
  empty-string vs. `None` ambiguity — the endpoint normalizes an empty
  submitted string to `None`).

## Design System (SOL) Application

`app/static/app.css` is rebuilt from `docs/superpowers/DESIGN.md`'s
tokens: CSS custom properties for the color palette, typography scale,
spacing scale, and corner radii, plus component classes for buttons,
cards/rows, badges/pills, and inputs following SOL's component
guidance (flat hairline-bordered cards, solid-blue primary actions,
tight radii, uppercase-tracked labels/eyebrows). Every existing
template (`base.html`, `tasks/*`, `calendar/*`, `labels/*`,
`reminders/*`) is updated to use these classes, so Slice 1's
previously-unstyled UI and Slice 2's new elements (Archive button,
completion-note field, History view, status nav) share one consistent
look. No behavioral change from this — purely presentational.

## Testing

- Backend: `record_change` unit-tested directly (writes the expected
  row); `complete_task` tested with and without a note; `reschedule_task`
  tested to confirm it writes a `due_date` log entry with the correct
  old/new values; `archive_task` tested for the `done`-only precondition
  (404 on an open or already-archived task) and for successfully moving
  a task out of Open/Done views into the Archived view; `list_tasks`
  tested for `400` on an invalid `status` value; `GET /tasks/{id}/history`
  tested for ordering and for including the completion note.
- Visual: no automated tests for the CSS restyle (this is a local
  server-rendered app, not a component-tested frontend) — a manual
  browser pass across all views (task list, calendar, labels, reminders,
  history) after implementation, per the pattern established in Slice 1.

## Roadmap After This Slice

1. ~~Slice 1: Personal Workflow & Commitment Engine~~ *(shipped)*
2. ~~Slice 2: Confidence, History & Follow-Through~~ *(this spec)*
3. Slice 3: BA Traceability Workspace — requirements, stakeholders,
   decisions, risks, traceability matrix, gap detection, impact analysis,
   project summary reports.
4. Slice 4: Multi-User & Multi-Device — auth, real multi-user workspaces,
   a general shared file area, cross-device sync, conflict resolution.
