from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def test_create_label(client):
    response = client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})
    assert response.status_code == 200
    assert b"Urgent" in response.content


def test_rename_label(client, db_session):
    from app.models import Label

    client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})
    label = db_session.query(Label).filter_by(name="Urgent").one()

    response = client.patch(f"/labels/{label.id}", data={"name": "High Priority"})
    assert response.status_code == 200
    assert b"High Priority" in response.content

    db_session.refresh(label)
    assert label.name == "High Priority"


def test_delete_label_removes_it_but_keeps_task(client, db_session):
    from app.models import Label, Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})

    task = db_session.query(Task).filter_by(title="Draft outline").one()
    label = db_session.query(Label).filter_by(name="Urgent").one()
    client.post(f"/tasks/{task.id}/labels", data={"label_id": label.id})

    response = client.delete(f"/labels/{label.id}")
    assert response.status_code == 200

    db_session.expire_all()
    assert db_session.query(Label).filter_by(id=label.id).first() is None
    remaining_task = db_session.query(Task).filter_by(id=task.id).one()
    assert remaining_task.labels == []


def test_assign_label_to_task(client, db_session):
    from app.models import Label, Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})

    task = db_session.query(Task).filter_by(title="Draft outline").one()
    label = db_session.query(Label).filter_by(name="Urgent").one()

    response = client.post(f"/tasks/{task.id}/labels", data={"label_id": label.id})
    assert response.status_code == 200
    assert b"Urgent" in response.content

    db_session.refresh(task)
    assert [l.name for l in task.labels] == ["Urgent"]
