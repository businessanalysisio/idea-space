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
