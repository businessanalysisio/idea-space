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
    # The redesigned matrix shows per-category link COUNTS, not names — one
    # linked item per category renders as a "partial"-tier badge (0 would be
    # "missing", 2+ would be "linked").
    assert "Req with links" in body
    assert body.count("link-badge--partial") == 4
    assert "link-badge--missing" not in body


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
    assert response.content.count(b"link-badge--missing") == 4


def test_matrix_page_shows_coverage_metrics(client):
    response = client.get("/matrix")
    assert response.status_code == 200
    body = response.text
    assert "COVERAGE" in body
    assert "ORPHANED" in body
    assert "VERIFIED" in body


def test_matrix_zero_requirements_renders_zero_percent_without_error(client):
    response = client.get("/matrix")
    assert response.status_code == 200
    assert "0%" in response.text


def test_matrix_link_cell_color_tiers(client, db_session):
    from app.models import Requirement, Stakeholder

    client.post("/stakeholders", data={"name": "Jane", "role": "Sponsor"})
    stakeholder = db_session.query(Stakeholder).filter_by(name="Jane").one()

    client.post("/requirements", data={"title": "Coverage test req"})
    requirement = db_session.query(Requirement).filter_by(title="Coverage test req").one()

    client.post(
        f"/requirements/{requirement.id}/stakeholders",
        data={"stakeholder_id": stakeholder.id},
    )

    response = client.get("/matrix")
    assert response.status_code == 200
    assert "link-badge--partial" in response.text or "link-badge--linked" in response.text
    assert "link-badge--missing" in response.text


def test_matrix_needs_attention_lists_at_risk_before_draft(client, db_session):
    from app.models import Requirement, Risk

    client.post("/requirements", data={"title": "At risk req", "status": "approved"})
    at_risk_requirement = db_session.query(Requirement).filter_by(title="At risk req").one()

    client.post("/risks", data={"title": "Bad vendor", "severity": "high", "status": "open"})
    risk = db_session.query(Risk).filter_by(title="Bad vendor").one()

    client.post(f"/requirements/{at_risk_requirement.id}/risks", data={"risk_id": risk.id})
    client.post("/requirements", data={"title": "Draft req with no links"})

    response = client.get("/matrix")
    assert response.status_code == 200
    body = response.text
    # "At risk req" also appears in the main table, which renders before the
    # attention panel — scope the ordering check to inside the panel itself.
    attention_section = body[body.index("NEEDS ATTENTION"):]
    at_risk_idx = attention_section.index("At risk req")
    draft_idx = attention_section.index("Draft req with no links")
    assert at_risk_idx < draft_idx
