# Idea Space — BA Traceability Workspace Foundation (Slice 3a) — Design Spec

**Date:** 2026-09-20
**Status:** Approved for implementation planning

## Context

Slices 1-2 shipped the Personal Workflow & Commitment Engine (recurring
tasks, calendar, labels, reminders) and Confidence, History & Follow-Through
(activity log, completion notes, archiving, SOL design system). This spec
covers **Slice 3a**, the first sub-slice of Slice 3 (BA Traceability
Workspace) per the roadmap — the product's stated primary job: *"When I
need to prove that analysis is complete, I want to trace every requirement
from business need through delivery, so I can reduce omissions and
rework."*

Slice 3 itself was too large for one spec — it bundles four independent
JTBDs (Close Traceability Gaps, Validate Stakeholder Alignment, Control
Change Impact, Communicate Status) that all depend on the same underlying
entities and traceability links existing first. This spec builds that
foundation only:

1. **Slice 3a: Foundation** — core entities (Requirement, Stakeholder,
   Decision, Risk), how they link to each other and to `Task`, and a
   read-only traceability matrix view. *(this spec)*
2. Slice 3b: Close Traceability Gaps — missing-field highlighting, quick-fix
   actions.
3. Slice 3c: Validate Stakeholder Alignment — approval state tracking,
   stakeholder comments.
4. Slice 3d: Control Change Impact — impact assessment view for downstream
   junction records.
5. Slice 3e: Communicate Status — exportable project summary report.

## Goals (Slice 3a)

- CRUD for four new entities: `Requirement`, `Stakeholder`, `Decision`,
  `Risk`.
- Many-to-many linking between `Requirement` and each of `Stakeholder`,
  `Decision`, `Risk`, and the existing `Task` model (Slice 1) — the same
  join-table pattern already used for `Task`↔`Label`.
- A read-only traceability matrix (`GET /matrix`): one row per requirement,
  showing its linked stakeholders, decisions, risks, and tasks.
- A real navigation bar in `base.html` (Tasks / Calendar / Requirements),
  since this is the first second-major-section the app has had — until now
  users navigated between `/tasks` and `/calendar` only via direct URLs.

Explicitly out of scope for this slice: gap/missing-field detection
(Slice 3b), stakeholder approval workflow and comments (Slice 3c), impact
assessment before saving a change (Slice 3d), exportable reports
(Slice 3e), and a dedicated "Business Need" entity (captured as a free-text
field on `Requirement` instead, per the decision below).

## Data Model

- `Requirement`: `id, workspace_id, owner_id (User), title, description
  (Text), business_need (Text), acceptance_criteria (Text), status
  (String, default "draft"), created_at`. `business_need` is a free-text
  field rather than a separate entity — simpler for this foundation slice;
  can be promoted to a real entity later if requirements turn out to
  genuinely share needs in practice.
- `Stakeholder`: `id, workspace_id, name, role, contact_info (nullable)`.
- `Decision`: `id, workspace_id, title, rationale (Text), decided_at
  (Date), decided_by (String, free text — not a Stakeholder FK, since a
  decision-maker isn't always a tracked stakeholder)`.
- `Risk`: `id, workspace_id, title, description (Text), severity
  ("low"|"medium"|"high"), likelihood ("low"|"medium"|"high"), mitigation
  (Text, nullable), status ("open"|"mitigated"|"closed", default "open")`.
- Junction tables (all many-to-many, mirroring `TaskLabel`'s composite-key
  pattern): `RequirementStakeholder(requirement_id, stakeholder_id)`,
  `RequirementDecision(requirement_id, decision_id)`,
  `RequirementRisk(requirement_id, risk_id)`,
  `RequirementTask(requirement_id, task_id)`.
- All four entities carry `workspace_id`, matching the future-proofing
  convention established since Slice 1 (single default workspace seeded,
  ready for Slice 4's multi-workspace support without rework).

## Architecture

- `app/routers/requirements.py`, `stakeholders.py`, `decisions.py`,
  `risks.py` — one router per entity, each following the existing
  `labels.py` router's shape: `POST /<entity>` (create), `PATCH
  /<entity>/{id}` (edit), `DELETE /<entity>/{id}` (delete — removing only
  that entity's junction rows, never cascading into linked requirements or
  tasks, matching the Slice 1 label-delete convention).
- Assignment endpoints on the `Requirement` side: `POST
  /requirements/{id}/stakeholders`, `.../decisions`, `.../risks`,
  `.../tasks` — each mirrors `POST /tasks/{id}/labels`'s idempotent
  append-if-absent behavior.
- `GET /requirements` — list/detail views (a list page plus a per-requirement
  detail page showing its description, business need, acceptance criteria,
  and all four linked-entity sections with inline assign forms).
- `GET /matrix` — a new router or an addition to `requirements.py`;
  read-only, queries all requirements with their linked entities eagerly
  loaded, renders one row per requirement with columns for stakeholder
  names, decision titles, risk titles, and task titles (or an empty-state
  placeholder per column when nothing's linked — still no "this is a gap"
  styling or logic, that's Slice 3b).
- `app/templates/base.html` gains a nav bar (`<nav class="main-nav">` with
  links to `/tasks`, `/calendar`, `/requirements`) styled with the existing
  SOL tokens from Slice 2, replacing the current bare `<header>` with
  just a title.

## Key Flows

1. **Create/edit/delete each entity**: a form per entity (title/role/etc.
   fields), listed with inline rename/delete controls — same shape as the
   Slice 1/2 label-manager panel.
2. **Link entities to a requirement**: on a requirement's detail page, a
   small assign form per linked-entity type (a `<select>` of all
   stakeholders/decisions/risks/tasks + an "Add" button), matching the
   per-task label-assign control from Slice 1.
3. **View the matrix**: navigate to `/matrix`, see every requirement as a
   row with its linked entities as columns; click a requirement's title to
   jump to its detail page.

## Error Handling & Edge Cases

- Deleting a `Stakeholder`/`Decision`/`Risk`/unlinking a `Task` removes
  only the relevant junction rows — the requirement and the other side of
  the link are untouched (same convention as Slice 1's label deletion,
  including the fix for the orphaned-join-row bug found in that slice's
  review — this slice's delete endpoints will explicitly delete matching
  junction rows before deleting the parent row, not rely on any implicit
  cascade).
- Assigning an already-linked entity to a requirement is idempotent (no
  duplicate junction row, no error) — same convention as label assignment.
- `Risk.severity`/`Risk.likelihood`/`Requirement.status` are validated
  against their allowed value sets on write, returning `400` for an
  invalid value (matching the `list_tasks` status-validation convention
  established in Slice 2, applied proactively here rather than
  discovered in review).
- The matrix view handles a requirement with zero links in every category
  without error (renders the empty-state placeholder columns).

## Testing

- CRUD tests per entity (create/edit/delete, delete-doesn't-orphan-parent).
- Assignment tests per junction table (idempotent double-assign, unlink
  removes only the junction row).
- Validation tests for the three constrained-value fields (`severity`,
  `likelihood`, `status`) rejecting invalid input with `400`.
- Matrix view test: a requirement with links in all four categories
  renders all linked names/titles; a requirement with no links renders the
  empty-state placeholders without error.
- Manual browser verification of the new nav bar and matrix view, per the
  pattern established in Slices 1-2.

## Roadmap After This Slice

1. ~~Slice 1: Personal Workflow & Commitment Engine~~ *(shipped)*
2. ~~Slice 2: Confidence, History & Follow-Through~~ *(shipped)*
3. Slice 3: BA Traceability Workspace
   - ~~3a: Foundation (entities, links, matrix)~~ *(this spec)*
   - 3b: Close Traceability Gaps
   - 3c: Validate Stakeholder Alignment
   - 3d: Control Change Impact
   - 3e: Communicate Status
4. Slice 4: Multi-User & Multi-Device
