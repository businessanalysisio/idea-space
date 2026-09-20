# Idea Space — Session History & Decision Log

**Covers:** 2026-09-19 through 2026-09-20
**Purpose:** A record of what was built, why, in what order, and how — so a
future session (human or Claude) can pick this project back up without
re-deriving decisions that were already made and validated here.

---

## 1. What This Project Is

**Idea Space** is a local-first Business Analyst project workspace, started
from a pasted "master JTBD backlog" describing the product's stated primary
job:

> "When I need to prove that analysis is complete, I want to trace every
> requirement from business need through delivery, so I can reduce
> omissions and rework."

The master backlog covered a broader surface (personal workflow, history
and follow-through, and BA traceability depth) than any single build
could tackle at once, so the first real decision of this session was to
**decompose it into a vertical-slice roadmap** rather than build
everything at once:

1. **Slice 1** — Personal Workflow & Commitment Engine
2. **Slice 2** — Confidence, History & Follow-Through
3. **Slice 3** — BA Traceability Workspace, itself decomposed into:
   - 3a Foundation → 3b Close Traceability Gaps → 3c Validate Stakeholder
     Alignment → 3d Control Change Impact → 3e Communicate Status
4. **Slice 4** — Multi-User & Multi-Device (not yet started)

Each slice was chosen to be independently shippable, produce working
software on its own, and build toward the primary job rather than toward
a feature checklist.

**Stack (decided during Slice 1's brainstorm):** Python, FastAPI,
server-rendered UI (Jinja2 + htmx — no separate frontend build), SQLite
for local storage (later made Postgres-portable for deployment — see
§6), pytest for testing.

---

## 2. Timeline of Work

### 2.1 Slice 1 — Personal Workflow & Commitment Engine (2026-09-19)

Brainstormed from the master backlog (architectural path: clarifying
questions on scope, then a written design). Delivered: tasks with due
dates, recurrence, labels, a calendar view, and reminders. Spec:
`docs/superpowers/specs/2026-09-19-personal-workflow-engine-design.md`;
plan: `docs/superpowers/plans/2026-09-19-personal-workflow-engine.md`
(11 tasks).

**Two real bugs found and fixed during this slice's execution** (both
became standing lessons applied proactively to every later slice):

- **htmx full-page duplication.** An htmx `outerHTML` swap inserts every
  top-level node in the response. A template that extended `base.html`
  (a full page) as an htmx-swap target produced duplicated headers/nav on
  every mutation. Fixed by extracting single-root fragment templates
  (e.g. `_task_list_only.html` with exactly one root `<ul>`). This became
  a **Global Constraint** applied from the start of every plan written
  after this: every htmx-targeted template must be single-root.
- **Orphaned junction rows on delete.** Deleting a `Label` didn't clean
  up its `TaskLabel` junction rows first, so a new label reusing the
  deleted row's id inherited stale associations. Fixed by always
  explicitly deleting junction rows before deleting the parent — also
  became a standing convention for every later many-to-many relationship.

Also hit and fixed: SQLAlchemy 2.0.35 had a real bug with
`Mapped[X | None]` on Python 3.14 — pinned to 2.0.54.

### 2.2 Slice 2 — Confidence, History & Follow-Through (2026-09-19–20)

Added: activity/audit log, completion notes on tasks, archiving (a real
`archived` status, not a soft-delete flag), and a full visual restyle of
the app using a pre-existing design-token file
(`docs/superpowers/DESIGN.md`, a Material-You-style "executive business
reviews" palette — this became the **SOL design system**, later fully
replaced — see §2.4). Spec:
`docs/superpowers/specs/2026-09-20-history-follow-through-design.md`;
plan: `docs/superpowers/plans/2026-09-20-history-follow-through.md`
(7 tasks).

**Two Criticals found in this slice's final whole-branch review:**

- The completion-note UI literally didn't exist yet (the "Done" button
  had no note field) — added, gated to open tasks.
- No migration path for the new `completion_note` column on an existing
  database — `Base.metadata.create_all()` only creates missing *tables*,
  never adds columns to existing ones. Fixed with a hand-rolled,
  idempotent `ensure_completion_note_column()` helper (`PRAGMA
  table_info` + `ALTER TABLE ... ADD COLUMN`, guarded so it's a no-op on
  an already-migrated database) run at startup. **Decision:** no Alembic
  — this hand-rolled pattern was judged sufficient for a local-first
  single-table-at-a-time app, and was reused for every later schema
  change in this session, including the eventual production deployment.

### 2.3 Slice 3a — BA Traceability Workspace Foundation (2026-09-20)

The first sub-slice of the product's actual primary job. Added:
`Requirement`, `Stakeholder`, `Decision`, `Risk` entities, many-to-many
links between them and `Task`, and a read-only traceability matrix. Spec:
`docs/superpowers/specs/2026-09-20-ba-traceability-foundation-design.md`;
plan:
`docs/superpowers/plans/2026-09-20-ba-traceability-foundation.md`
(8 tasks).

**Key decisions made during brainstorming, by explicit user choice:**
- `business_need` is a free-text field on `Requirement`, not its own
  entity (simpler for the foundation slice; can be promoted later if
  requirements turn out to genuinely share needs).
- All new junction tables use composite primary keys (matching the
  existing `TaskLabel` pattern), not surrogate ids.
- Every link (Stakeholder/Decision/Risk/Task ↔ Requirement) is
  many-to-many.

**Bugs and gaps found and fixed:**
- A real FastAPI gotcha caught during the controller's own pre-dispatch
  review (before any task was even started): an injected `response:
  Response` parameter's header mutations are **not** merged into a
  separately-returned `Response()` object — verified empirically. Fixed
  by constructing the `Response` directly with its headers, applied to
  `delete_requirement`'s `HX-Redirect`.
- Task 4's risk-edit-form was missing `description`/`mitigation` inputs,
  silently wiping those fields on every save — a genuine defect in the
  plan's own template text, not an implementer deviation. Fixed in both
  the plan and the implementation.
- Final review found two Important gaps: (1) `PATCH /decisions/{id}`
  500'd on an empty/invalid date (unguarded `date.fromisoformat`) — fixed
  with a 400 guard; (2) **no unlink capability existed anywhere** — the
  spec's own Error Handling and Testing sections *described* unlinking,
  but it was never actually designed into the Key Flows/plan. Ruled: a
  genuine spec-writing gap, closed by implementing the four unlink
  endpoints rather than retroactively weakening the spec, since an
  append-only traceability graph would be a real daily-use problem for a
  BA tool.

Slices 1, 2, and 3a were each executed via the full
**brainstorm → spec → plan → Subagent-Driven Development → final
whole-branch review → merge** cycle (see §5 for what each skill did).

### 2.4 Product Ops Redesign (2026-09-20)

The user supplied a complete visual mockup (dark theme, purple accent,
sidebar navigation, dashboard-style stat cards — the "Product Ops"
theme) and asked for a full UI rebuild, going beyond a pure reskin into
new behavior (a NOW/NEXT/DONE task board, a month-view calendar, computed
traceability status on the matrix). Classified as a redesign of existing
screens (not a new JTBD slice), so it got a design spec
(`docs/superpowers/specs/2026-09-20-product-ops-redesign-design.md`) and
plan (`docs/superpowers/plans/2026-09-20-product-ops-redesign.md`,
8 tasks) but no new roadmap entry.

**Explicit scope decisions, made by the user via a clarifying question
before any code was touched:**
- **No new "Test"/verification entity** — the mockup's matrix showed a
  "Tests" column, but the app tracks Stakeholders, not tests; adding a
  whole new entity would be a new subsystem, not a redesign. The matrix
  kept **Stakeholders** as its 4th column instead.
- **No real search** — the sidebar/topbar search box is decorative.
- **No multi-user owner picker** — only one seeded user exists until
  Slice 4; shown as a fixed value, not a real dropdown.
- Icons from the mockup (inline lucide SVGs) were **not** reproduced
  pixel-for-pixel — CSS shapes/typography instead, to keep every task's
  template code focused on structure.

**Execution via Subagent-Driven Development** (8 tasks: schema
migration → design tokens/shell → shared `traceability_status` helper →
Tasks board → Calendar views → Requirements dashboard → Traceability
matrix → manual verification). Notable findings along the way:

- Two real bugs were found **in the plan's own prescribed code**, not
  introduced by implementers: a Jinja2 `dict.items()` attribute-lookup
  gotcha (`day.items` silently resolved to the dict's `.items()` method
  instead of a `"items"` key, since Jinja2 tries `getattr` before
  falling back to `[]` access — fixed with explicit bracket access), and
  a CSS class-name collision (`.calendar-day-number` shared a prefix
  with `.calendar-day`, double-counting cells in the plan's own test).
- The **final whole-branch review** (dispatched on the most capable
  model, as required for that step) found 3 Important, cross-task
  findings that no single task's narrower review could have caught:
  1. The full task-creation form (recurrence, reminders) was left
     unreachable in the UI after the board rebuild — the *spec* called
     for a `<details>` disclosure to reach it, but the *plan* never
     actually included one.
  2. `.task--virtual` (marking projected recurring calendar occurrences)
     lost its CSS rule in the theme rewrite and was never re-added.
  3. The archived-tasks view was left broken — two of its controls still
     targeted an htmx swap id (`#task-list`) that no longer existed
     after the board rewrite, and its CSS classes had been deleted with
     no replacement.

  All three, plus 5 smaller cleanup items (dead code, an orphaned
  template, a dropped `completion_note` input, a duplicate CSS class, a
  dropped explanatory comment) were fixed in **one fix wave** (the
  process's own rule: no second wave). The fix-wave implementer
  completed all the work and even ran the full suite green, but hit an
  API rate-limit error immediately before its own `git commit` — the
  controller independently re-verified the suite and the trickiest
  diffs, then completed that one interrupted step itself (not new
  implementation work, just finishing an already-decided, already-tested
  action after an infrastructure failure). A scoped re-review then
  independently confirmed everything.

  **Deliberately not fixed**, ruled acceptable to ship: 9 smaller Minor
  findings (stale dashboard metrics after creating a requirement,
  the active label filter resetting after a board mutation, a few
  cosmetic items) — deferred to a follow-up rather than blocking merge.

### 2.5 Task Editing (2026-09-20)

A small, user-requested, bounded addition (not a new slice): the ability
to edit a task's title and due date directly from its card, rather than
only via calendar drag-and-drop. New `PATCH /tasks/{id}` endpoint plus an
inline "Edit" disclosure on each card. Both changes are logged to the
existing activity history, matching how every other task mutation is
tracked. 5 new tests, no plan document (bounded-path: brainstorm →
present design in chat → approval → implement directly).

### 2.6 GitHub Push & Vercel Deployment (2026-09-20)

The user asked to push to GitHub and deploy to Vercel "with a real
database connection." Before touching anything external, three
architecture facts were surfaced and confirmed with the user first:

- The app had **no GitHub remote** yet — this meant creating a new repo,
  not pushing to an existing one.
- **SQLite doesn't work on Vercel's serverless filesystem** — nothing
  persists between invocations. "Real database" necessarily meant
  migrating to a hosted Postgres.
- **The app has no authentication at all** (multi-user/login is the
  explicitly-deferred Slice 4) — deployed publicly with a real database
  and no gate, anyone with the URL would have full read/write/delete
  access to everything.

**User's decisions (via clarifying question):** public GitHub repo,
Vercel Postgres (via its managed Neon integration) as the database
provider, and a simple shared-password gate added before going public.

**Code changes made to prepare for deployment:**
- `app/db.py`: reads `DATABASE_URL` when set (rewriting `postgres://`
  and bare `postgresql://` to the explicit `postgresql+psycopg://`
  driver this app uses), falling back to local SQLite when unset — so
  local dev and the test suite are completely unaffected.
- `app/main.py`: the SQLite-specific `PRAGMA`-based migration helpers
  (`ensure_completion_note_column`, `ensure_redesign_columns`) are now
  guarded to no-op on any non-SQLite dialect — a freshly provisioned
  Postgres database has no legacy rows to migrate from; `create_all`
  alone gives it every column the current models define.
- `app/middleware.py` (new): a `SitePasswordMiddleware` — one shared
  password via HTTP Basic Auth, controlled by a `SITE_PASSWORD`
  environment variable, off by default (so it never affects local dev or
  tests), and explicitly bypassing `/health` so uptime checks keep
  working.
- `vercel.json` (new): Python function entrypoint configuration.
- `requirements.txt`: added `psycopg[binary]` (psycopg v3 — psycopg2-binary
  has no prebuilt wheel for this environment's Python 3.14 yet).
- `.env.example` (new): documents `DATABASE_URL` and `SITE_PASSWORD`.
- Root `.gitignore`: added `.env`, `.env.local`, `.vercel` before the
  repo ever went public, so no local secrets or project-link metadata
  can land in a public commit.

**A real production bug was found and fixed after the first deploy,**
live: the very first deploy crashed every single route (including
`/health`) with a 500. Root cause: concurrent serverless cold starts each
ran `Base.metadata.create_all()` against the same brand-new Postgres
database at once; two simultaneous `CREATE TABLE` statements for the
same table both passed SQLAlchemy's own "does it exist" check before one
of them lost the race and raised a duplicate-object error, which aborted
the *entire* startup sequence for that invocation (SQLite never hit this,
being single-writer). Fixed by creating tables one at a time and
tolerating exactly that race per table, so one table losing its race
doesn't stop the rest of the schema from being created in the same
invocation. Redeployed and independently verified end-to-end: health
check, all three password-gate cases (no credentials / wrong password /
correct password), and an actual create-then-read round trip against the
live Postgres database.

**One deliberately-deferred, non-blocking finding from this pass:**
`seed_default_workspace`'s "check if the default workspace exists, else
create it" logic has the same check-then-create shape as the schema-race
bug, just without a unique constraint to turn a race into a visible
error — under concurrent cold starts it could theoretically create two
default workspace rows instead of one. Flagged, not fixed (no crash, low
real-world impact, scope was already large).

---

## 3. Key Decisions & Rationale (quick-reference index)

| Decision | Why | Where |
|---|---|---|
| Decompose the master backlog into vertical slices | Independent, shippable increments beat one giant build | §1 |
| Server-rendered Jinja2 + htmx, no frontend build | Matches "local-first" scope; simplest stack that supports the JTBDs | Slice 1 brainstorm |
| Every htmx-targeted template must be single-root | `outerHTML` swap inserts every top-level node — found the hard way in Slice 1 | §2.1 |
| Junction-row deletes are always explicit, never implicit cascade | Found a real orphaned-row bug in Slice 1 | §2.1 |
| Hand-rolled idempotent migrations, no Alembic | Judged sufficient for this app's single-table-at-a-time schema changes | §2.2 |
| `business_need` is a free-text field, not an entity | Simpler for the traceability foundation slice; promote later if needed | §2.3 |
| Matrix's 4th column is Stakeholders, not a new "Tests" entity | A new entity is a new subsystem, not a redesign | §2.4 |
| No real search, no multi-user picker in the redesign | Explicit Non-Goals — multi-user is Slice 4, not yet built | §2.4 |
| Public GitHub repo | User's explicit choice | §2.6 |
| Vercel Postgres (Neon) over SQLite for deployment | SQLite doesn't persist on serverless; user's explicit choice | §2.6 |
| Shared-password gate before going public | App has no real auth yet; user's explicit choice, to avoid a wide-open public database | §2.6 |
| No Alembic even in production | Extended the same hand-rolled pattern, now dialect-guarded | §2.6 |

---

## 4. Process: How Requirements Were Actually Defined

Every substantial piece of work in this session went through the same
discipline, not ad hoc coding:

1. **Brainstorm** — classify the request (spike / bounded /
   architectural), ask clarifying questions one at a time, propose
   approaches, and *get explicit approval before writing any code*. This
   gate was never skipped, including for the redesign and the deployment
   work, both of which surfaced real architecture questions the user
   needed to decide (not just rubber-stamp).
2. **Write a spec** (architectural-scope work only) — a design document
   covering context, goals, non-goals, data model, architecture, key
   flows, error handling, and testing. Self-reviewed for placeholders,
   internal contradictions, and scope before the user ever saw it.
3. **Write a plan** — every task fully specified (exact files, exact
   code, exact tests) so an implementer with zero context on this
   codebase could execute it without guessing. Self-reviewed against the
   spec for coverage gaps and placeholder text.
4. **Execute** — for slice-sized work, via Subagent-Driven Development
   (see §5): a fresh implementer per task, a fresh reviewer per task,
   and rulings recorded (not silently made) whenever the plan and
   reality disagreed. For small bounded work (task editing), directly in
   the main session with the same TDD discipline.
5. **Final whole-branch review** — one broad review after all tasks
   land, specifically because narrower per-task reviews have
   *repeatedly* missed cross-task integration gaps in this session (the
   orphaned task-creation form, the missing CSS rule, and the broken
   archived view were all caught here, not earlier).
6. **Merge, with the user choosing how** — every branch finish presented
   the same explicit choice (merge locally / push a PR / keep as-is) and
   waited for the user's answer rather than assuming.

Every ruling made *for* the user during autonomous execution (a plan
ambiguity resolved, a test adjusted, a scope decision taken) was recorded
in that slice's SDD ledger as it happened and reported back at the end —
nothing was decided silently.

---

## 5. Tools, Skills & Plugins Used

| Skill / Tool | What it actually did in this session |
|---|---|
| `superpowers:brainstorming` | Gated every new body of work behind explicit scope classification and user approval before any code was written — used for Slices 1–3a, the redesign, and (bounded path) task editing. |
| `superpowers:writing-plans` | Turned each approved spec into a fully-specified, no-placeholder implementation plan — self-reviewed for spec coverage and internal consistency before execution began. |
| `superpowers:using-git-worktrees` | Isolated every non-trivial change in its own git worktree/branch, so master was never touched directly by in-progress work. |
| `superpowers:subagent-driven-development` | Ran the fresh-implementer / fresh-reviewer / fix-loop / final-review cycle for every slice and the redesign — the mechanism that caught nearly every bug described above, most of them *before* they reached the user. |
| `superpowers:finishing-a-development-branch` | Standardized every merge decision: run tests, present the same 3 options, execute the user's actual choice, clean up the worktree. |
| `vercel:bootstrap` | Referenced for the intended provisioning order (link → provision Postgres → verify env → bootstrap) — adapted from its Node.js-oriented defaults to this Python project. |
| `vercel:deploy` | Preflight checks (auth, linkage, uncommitted changes) and the production-deploy confirmation discipline before shipping to a live URL. |
| `vercel:vercel-functions` | Clarified how Vercel's Python runtime resolves a FastAPI entrypoint (keyed on the app file itself, e.g. `app/main.py`, not on `/api` routes) — shaped `vercel.json`. |
| `gh` CLI | Created the public GitHub repository and pushed. |
| `vercel` CLI | Authenticated (via device-code flow), linked the project, provisioned Postgres via the Neon integration, set the `SITE_PASSWORD` secret, and deployed. |
| Chrome browser automation | Used throughout for manual, in-browser verification of each shipped slice and the redesign (metrics rendering, drag-and-drop, filters, CSV export, etc.), alongside the automated test suite. |

---

## 6. Architecture Summary (current state)

- **Backend:** FastAPI, routers per entity (`tasks`, `calendar`, `labels`,
  `reminders`, `stakeholders`, `decisions`, `risks`, `requirements`,
  `matrix`), SQLAlchemy 2.0.54 ORM throughout except two dialect-guarded
  raw-SQL migration helpers.
- **Database:** SQLAlchemy engine selects Postgres (via `DATABASE_URL`,
  psycopg v3 driver) when set, else local SQLite — same codebase, same
  test suite, works identically either way. Schema managed by
  `Base.metadata.create_all()` at startup plus two idempotent,
  SQLite-only incremental-migration helpers for columns added after the
  original tables existed.
- **Frontend:** Jinja2 templates, htmx for all mutation/interaction (no
  client-side framework), a shared dark "Product Ops" design-token CSS
  file (`app/static/app.css`) as of §2.4.
- **Auth:** none per-user (Slice 4, not built). A single shared-password
  HTTP Basic Auth gate (`app/middleware.py`) protects the whole
  deployed app when `SITE_PASSWORD` is set; local dev and tests run with
  it unset and unaffected.
- **Testing:** pytest, `client`/`db_session` fixtures (fresh in-memory
  SQLite per test, from `tests/conftest.py`) — **157 tests passing** as
  of the last commit in this session.
- **Deployment:** Vercel (Python serverless function, entrypoint
  `app/main.py`), Postgres via Vercel's managed Neon integration, GitHub
  repo at `https://github.com/businessanalysisio/idea-space` (public),
  live at `https://idea-space-fawn.vercel.app`.

---

## 7. Known Gaps / Deferred Follow-Ups

Nothing here is broken; these are explicit, recorded decisions to defer
rather than gaps anyone missed:

- **Requirements dashboard metrics go stale after creating a
  requirement** until the page is reloaded (only the list re-renders,
  not the metric cards) — Product Ops redesign, deferred minor.
- **The active label filter on the Tasks board resets after any
  mutation** (complete/block/label-assign) — same as the pre-redesign
  behavior, not a new regression, deferred minor.
- **`seed_default_workspace` has an unguarded check-then-create race**
  under concurrent cold starts (§2.6) — no unique constraint to catch it,
  so it could theoretically create duplicate default-workspace rows.
  Not a crash; not yet fixed.
- **Slice 3b–3e** (Close Traceability Gaps, Validate Stakeholder
  Alignment, Control Change Impact, Communicate Status) and **Slice 4**
  (Multi-User & Multi-Device) are on the roadmap but not started.
- **No real authentication** — the shared password is a stopgap for a
  public deployment, not a substitute for the per-user auth Slice 4 is
  meant to add.

---

## 8. Current Deployment State (as of 2026-09-20)

- **Source:** `https://github.com/businessanalysisio/idea-space` (public)
- **Live app:** `https://idea-space-fawn.vercel.app`
- **Access:** HTTP Basic Auth, any username, shared password (stored as
  the `SITE_PASSWORD` secret in Vercel's Production and Preview
  environments — not repeated here; retrieve it from the Vercel
  dashboard or the session that generated it).
- **Database:** Postgres, provisioned via Vercel's Neon integration,
  connected through `DATABASE_URL`.
