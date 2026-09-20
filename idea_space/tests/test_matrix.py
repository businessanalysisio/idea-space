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
