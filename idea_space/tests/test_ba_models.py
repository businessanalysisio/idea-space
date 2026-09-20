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
