def test_create_risk(client):
    response = client.post(
        "/risks",
        data={"title": "Vendor API instability", "description": "...", "severity": "high", "likelihood": "medium"},
    )
    assert response.status_code == 200
    assert b"Vendor API instability" in response.content


def test_create_risk_rejects_invalid_severity(client):
    response = client.post(
        "/risks", data={"title": "Bad risk", "severity": "extreme", "likelihood": "medium"}
    )
    assert response.status_code == 400


def test_create_risk_rejects_invalid_status(client):
    response = client.post(
        "/risks",
        data={"title": "Bad risk", "severity": "high", "likelihood": "medium", "status": "ignored"},
    )
    assert response.status_code == 400


def test_edit_risk(client, db_session):
    from app.models import Risk

    client.post("/risks", data={"title": "Vendor risk", "severity": "high", "likelihood": "medium"})
    risk = db_session.query(Risk).filter_by(title="Vendor risk").one()

    response = client.patch(
        f"/risks/{risk.id}",
        data={
            "title": "Vendor risk",
            "severity": "low",
            "likelihood": "low",
            "status": "mitigated",
            "mitigation": "Switched vendors",
        },
    )
    assert response.status_code == 200

    db_session.refresh(risk)
    assert risk.status == "mitigated"
    assert risk.mitigation == "Switched vendors"


def test_delete_risk_removes_junction_rows(client, db_session):
    from app.models import Requirement, RequirementRisk, Risk
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    risk = Risk(workspace_id=workspace.id, title="Vendor risk", description="")
    db_session.add_all([requirement, risk])
    db_session.commit()
    requirement.risks.append(risk)
    db_session.commit()

    response = client.delete(f"/risks/{risk.id}")
    assert response.status_code == 200

    db_session.expire_all()
    assert db_session.query(Risk).filter_by(id=risk.id).first() is None
    remaining = db_session.query(RequirementRisk).filter_by(risk_id=risk.id).all()
    assert remaining == []
