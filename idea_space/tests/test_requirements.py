def test_get_requirements_returns_empty_list_page(client):
    response = client.get("/requirements")
    assert response.status_code == 200
    assert b"No requirements yet" in response.content


def test_create_requirement_returns_it_in_list(client):
    response = client.post(
        "/requirements",
        data={
            "title": "Users can log in with SSO",
            "description": "...",
            "business_need": "Reduce support tickets",
            "acceptance_criteria": "Given a corporate email, when...",
            "status": "draft",
        },
    )
    assert response.status_code == 200
    assert b"Users can log in with SSO" in response.content


def test_requirement_detail_page_renders(client, db_session):
    from app.models import Requirement
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    response = client.get(f"/requirements/{requirement.id}")
    assert response.status_code == 200
    assert b"Req 1" in response.content


def test_requirement_detail_unknown_id_returns_404(client):
    response = client.get("/requirements/999")
    assert response.status_code == 404


def test_edit_requirement(client, db_session):
    from app.models import Requirement
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    response = client.patch(
        f"/requirements/{requirement.id}",
        data={
            "title": "Req 1 Updated",
            "description": "",
            "business_need": "",
            "acceptance_criteria": "",
            "status": "approved",
        },
    )
    assert response.status_code == 200
    assert b"Req 1 Updated" in response.content

    db_session.refresh(requirement)
    assert requirement.status == "approved"


def test_edit_requirement_rejects_invalid_status(client, db_session):
    from app.models import Requirement
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    response = client.patch(
        f"/requirements/{requirement.id}",
        data={"title": "Req 1", "status": "banana"},
    )
    assert response.status_code == 400


def test_delete_requirement_redirects_and_cleans_all_junctions(client, db_session):
    from datetime import date, datetime, timezone

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

    UTC = timezone.utc
    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    stakeholder = Stakeholder(workspace_id=workspace.id, name="Jane", role="Sponsor")
    decision = Decision(
        workspace_id=workspace.id, title="Dec 1", rationale="", decided_at=date(2026, 9, 20), decided_by="Jane"
    )
    risk = Risk(workspace_id=workspace.id, title="Risk 1", description="")
    task = Task(
        workspace_id=workspace.id, owner_id=user.id, title="Task 1", due_date=datetime(2026, 9, 25, tzinfo=UTC)
    )
    db_session.add_all([requirement, stakeholder, decision, risk, task])
    db_session.commit()
    requirement.stakeholders.append(stakeholder)
    requirement.decisions.append(decision)
    requirement.risks.append(risk)
    requirement.tasks.append(task)
    db_session.commit()

    response = client.delete(f"/requirements/{requirement.id}", follow_redirects=False)
    assert response.status_code == 200
    assert response.headers.get("hx-redirect") == "/requirements"

    db_session.expire_all()
    assert db_session.query(Requirement).filter_by(id=requirement.id).first() is None
    assert db_session.query(RequirementStakeholder).filter_by(requirement_id=requirement.id).all() == []
    assert db_session.query(RequirementDecision).filter_by(requirement_id=requirement.id).all() == []
    assert db_session.query(RequirementRisk).filter_by(requirement_id=requirement.id).all() == []
    assert db_session.query(RequirementTask).filter_by(requirement_id=requirement.id).all() == []
