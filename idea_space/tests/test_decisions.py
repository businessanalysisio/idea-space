def test_create_decision(client):
    response = client.post(
        "/decisions",
        data={
            "title": "Use SSO",
            "rationale": "Reduces password reset burden",
            "decided_at": "2026-09-20",
            "decided_by": "Jane Sponsor",
        },
    )
    assert response.status_code == 200
    assert b"Use SSO" in response.content


def test_edit_decision(client, db_session):
    from app.models import Decision

    client.post(
        "/decisions",
        data={"title": "Use SSO", "rationale": "", "decided_at": "2026-09-20", "decided_by": "Jane"},
    )
    decision = db_session.query(Decision).filter_by(title="Use SSO").one()

    response = client.patch(
        f"/decisions/{decision.id}",
        data={
            "title": "Use SSO for all logins",
            "rationale": "Updated rationale",
            "decided_at": "2026-09-21",
            "decided_by": "Jane Sponsor",
        },
    )
    assert response.status_code == 200
    assert b"Use SSO for all logins" in response.content

    db_session.refresh(decision)
    assert decision.rationale == "Updated rationale"


def test_delete_decision_removes_junction_rows(client, db_session):
    from datetime import date

    from app.models import Decision, Requirement, RequirementDecision
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    decision = Decision(
        workspace_id=workspace.id,
        title="Use SSO",
        rationale="",
        decided_at=date(2026, 9, 20),
        decided_by="Jane",
    )
    db_session.add_all([requirement, decision])
    db_session.commit()
    requirement.decisions.append(decision)
    db_session.commit()

    response = client.delete(f"/decisions/{decision.id}")
    assert response.status_code == 200

    db_session.expire_all()
    assert db_session.query(Decision).filter_by(id=decision.id).first() is None
    remaining = (
        db_session.query(RequirementDecision).filter_by(decision_id=decision.id).all()
    )
    assert remaining == []


def test_create_decision_rejects_invalid_date(client):
    response = client.post(
        "/decisions",
        data={"title": "Bad decision", "rationale": "", "decided_at": "not-a-date", "decided_by": "Jane"},
    )
    assert response.status_code == 400


def test_edit_decision_rejects_empty_date(client, db_session):
    from app.models import Decision

    client.post(
        "/decisions",
        data={"title": "Use SSO", "rationale": "", "decided_at": "2026-09-20", "decided_by": "Jane"},
    )
    decision = db_session.query(Decision).filter_by(title="Use SSO").one()

    response = client.patch(
        f"/decisions/{decision.id}",
        data={"title": "Use SSO", "rationale": "", "decided_at": "", "decided_by": "Jane"},
    )
    assert response.status_code == 400
