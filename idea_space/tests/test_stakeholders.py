def test_create_stakeholder(client):
    response = client.post("/stakeholders", data={"name": "Jane Sponsor", "role": "Sponsor"})
    assert response.status_code == 200
    assert b"Jane Sponsor" in response.content


def test_edit_stakeholder(client, db_session):
    from app.models import Stakeholder

    client.post("/stakeholders", data={"name": "Jane Sponsor", "role": "Sponsor"})
    stakeholder = db_session.query(Stakeholder).filter_by(name="Jane Sponsor").one()

    response = client.patch(
        f"/stakeholders/{stakeholder.id}",
        data={"name": "Jane Smith", "role": "Executive Sponsor"},
    )
    assert response.status_code == 200
    assert b"Jane Smith" in response.content

    db_session.refresh(stakeholder)
    assert stakeholder.role == "Executive Sponsor"


def test_delete_stakeholder_removes_junction_rows(client, db_session):
    from app.models import Requirement, RequirementStakeholder, Stakeholder
    from app.seed import seed_default_workspace

    workspace, user = seed_default_workspace(db_session)
    requirement = Requirement(workspace_id=workspace.id, owner_id=user.id, title="Req 1")
    stakeholder = Stakeholder(workspace_id=workspace.id, name="Jane Sponsor", role="Sponsor")
    db_session.add_all([requirement, stakeholder])
    db_session.commit()
    requirement.stakeholders.append(stakeholder)
    db_session.commit()

    response = client.delete(f"/stakeholders/{stakeholder.id}")
    assert response.status_code == 200

    db_session.expire_all()
    assert db_session.query(Stakeholder).filter_by(id=stakeholder.id).first() is None
    remaining = (
        db_session.query(RequirementStakeholder)
        .filter_by(stakeholder_id=stakeholder.id)
        .all()
    )
    assert remaining == []
