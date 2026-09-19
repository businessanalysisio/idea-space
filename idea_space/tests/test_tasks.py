from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def test_get_tasks_returns_empty_list_page(client):
    response = client.get("/tasks")
    assert response.status_code == 200
    assert b"No tasks yet" in response.content


def test_create_task_returns_it_in_list(client):
    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    response = client.post(
        "/tasks",
        data={"title": "Draft requirements outline", "due_date": due},
    )
    assert response.status_code == 200
    assert b"Draft requirements outline" in response.content

    listing = client.get("/tasks")
    assert b"Draft requirements outline" in listing.content


def test_create_recurring_task_stores_recurrence_fields(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post(
        "/tasks",
        data={
            "title": "Weekly status update",
            "due_date": due,
            "recurrence_pattern": "weekly",
            "recurrence_interval": "1",
        },
    )

    task = db_session.query(Task).filter_by(title="Weekly status update").one()
    assert task.recurrence_pattern == "weekly"
    assert task.recurrence_active is True
    assert task.recurrence_series_id == task.id


def test_overdue_task_is_flagged(client):
    overdue_due = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Send follow-up email", "due_date": overdue_due})

    response = client.get("/tasks")
    assert b"task--overdue" in response.content
