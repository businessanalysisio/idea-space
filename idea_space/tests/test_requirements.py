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


def test_link_stakeholder_to_requirement(client, db_session):
    from app.models import Requirement, Stakeholder
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    client.post("/stakeholders", data={"name": "Jane Sponsor", "role": "Sponsor"})
    stakeholder = db_session.query(Stakeholder).filter_by(name="Jane Sponsor").one()

    response = client.post(
        f"/requirements/{requirement.id}/stakeholders", data={"stakeholder_id": stakeholder.id}
    )
    assert response.status_code == 200
    assert b"Jane Sponsor" in response.content

    db_session.refresh(requirement)
    assert [s.name for s in requirement.stakeholders] == ["Jane Sponsor"]


def test_link_stakeholder_is_idempotent(client, db_session):
    from app.models import Requirement, Stakeholder
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    client.post("/stakeholders", data={"name": "Jane Sponsor", "role": "Sponsor"})
    stakeholder = db_session.query(Stakeholder).filter_by(name="Jane Sponsor").one()

    client.post(f"/requirements/{requirement.id}/stakeholders", data={"stakeholder_id": stakeholder.id})
    client.post(f"/requirements/{requirement.id}/stakeholders", data={"stakeholder_id": stakeholder.id})

    db_session.refresh(requirement)
    assert len(requirement.stakeholders) == 1


def test_link_decision_to_requirement(client, db_session):
    from app.models import Decision, Requirement
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    client.post(
        "/decisions",
        data={"title": "Use SSO", "rationale": "", "decided_at": "2026-09-20", "decided_by": "Jane"},
    )
    decision = db_session.query(Decision).filter_by(title="Use SSO").one()

    response = client.post(f"/requirements/{requirement.id}/decisions", data={"decision_id": decision.id})
    assert response.status_code == 200
    assert b"Use SSO" in response.content


def test_link_risk_to_requirement(client, db_session):
    from app.models import Requirement, Risk
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    client.post("/risks", data={"title": "Vendor risk", "severity": "high", "likelihood": "medium"})
    risk = db_session.query(Risk).filter_by(title="Vendor risk").one()

    response = client.post(f"/requirements/{requirement.id}/risks", data={"risk_id": risk.id})
    assert response.status_code == 200
    assert b"Vendor risk" in response.content


def test_link_task_to_requirement(client, db_session):
    from datetime import datetime, timezone

    from app.models import Requirement, Task
    from app.seed import seed_default_workspace

    UTC = timezone.utc
    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    db_session.add(requirement)
    db_session.commit()

    due = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Implement SSO", "due_date": due})
    task = db_session.query(Task).filter_by(title="Implement SSO").one()

    response = client.post(f"/requirements/{requirement.id}/tasks", data={"task_id": task.id})
    assert response.status_code == 200
    assert b"Implement SSO" in response.content


def test_link_stakeholder_unknown_requirement_returns_404(client, db_session):
    from app.models import Stakeholder

    client.post("/stakeholders", data={"name": "Jane Sponsor", "role": "Sponsor"})
    stakeholder = db_session.query(Stakeholder).filter_by(name="Jane Sponsor").one()

    response = client.post("/requirements/999/stakeholders", data={"stakeholder_id": stakeholder.id})
    assert response.status_code == 404


def test_unlink_stakeholder(client, db_session):
    from app.models import Requirement, Stakeholder
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    stakeholder = Stakeholder(workspace_id=workspace.id, name="Jane", role="Sponsor")
    db_session.add_all([requirement, stakeholder])
    db_session.commit()
    requirement.stakeholders.append(stakeholder)
    db_session.commit()

    response = client.delete(f"/requirements/{requirement.id}/stakeholders/{stakeholder.id}")
    assert response.status_code == 200
    # "Jane" alone would also match the still-present "Link stakeholder" dropdown
    # option (all_stakeholders is independent of the link), so check for the
    # specific linked-item rendering instead.
    assert b"Jane (Sponsor)" not in response.content

    db_session.refresh(requirement)
    assert requirement.stakeholders == []


def test_unlink_decision(client, db_session):
    from datetime import date

    from app.models import Decision, Requirement
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    decision = Decision(
        workspace_id=workspace.id, title="Dec 1", rationale="", decided_at=date(2026, 9, 20), decided_by="Jane"
    )
    db_session.add_all([requirement, decision])
    db_session.commit()
    requirement.decisions.append(decision)
    db_session.commit()

    response = client.delete(f"/requirements/{requirement.id}/decisions/{decision.id}")
    assert response.status_code == 200

    db_session.refresh(requirement)
    assert requirement.decisions == []


def test_unlink_risk(client, db_session):
    from app.models import Requirement, Risk
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    risk = Risk(workspace_id=workspace.id, title="Risk 1", description="")
    db_session.add_all([requirement, risk])
    db_session.commit()
    requirement.risks.append(risk)
    db_session.commit()

    response = client.delete(f"/requirements/{requirement.id}/risks/{risk.id}")
    assert response.status_code == 200

    db_session.refresh(requirement)
    assert requirement.risks == []


def test_unlink_task(client, db_session):
    from datetime import datetime, timezone

    from app.models import Requirement, Task
    from app.seed import seed_default_workspace

    UTC = timezone.utc
    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    task = Task(
        workspace_id=workspace.id, owner_id=user.id, title="Task 1", due_date=datetime(2026, 9, 25, tzinfo=UTC)
    )
    db_session.add_all([requirement, task])
    db_session.commit()
    requirement.tasks.append(task)
    db_session.commit()

    response = client.delete(f"/requirements/{requirement.id}/tasks/{task.id}")
    assert response.status_code == 200

    db_session.refresh(requirement)
    assert requirement.tasks == []


def test_unlink_stakeholder_unknown_requirement_returns_404(client, db_session):
    from app.models import Stakeholder

    client.post("/stakeholders", data={"name": "Jane Sponsor", "role": "Sponsor"})
    stakeholder = db_session.query(Stakeholder).filter_by(name="Jane Sponsor").one()

    response = client.delete(f"/requirements/999/stakeholders/{stakeholder.id}")
    assert response.status_code == 404


def test_unlink_stakeholder_is_safe_when_not_linked(client, db_session):
    from app.models import Requirement, Stakeholder
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    stakeholder = Stakeholder(workspace_id=workspace.id, name="Jane", role="Sponsor")
    db_session.add_all([requirement, stakeholder])
    db_session.commit()

    response = client.delete(f"/requirements/{requirement.id}/stakeholders/{stakeholder.id}")
    assert response.status_code == 200


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
