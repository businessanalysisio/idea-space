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


def test_complete_non_recurring_task_removes_it_from_open_list(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "One-off review", "due_date": due})
    task = db_session.query(Task).filter_by(title="One-off review").one()

    response = client.post(f"/tasks/{task.id}/complete")
    assert response.status_code == 200
    assert b"One-off review" not in response.content

    db_session.refresh(task)
    assert task.status == "done"
    assert task.completed_at is not None


def test_completing_recurring_task_spawns_successor(client, db_session):
    from app.models import Task

    due = datetime(2026, 9, 20, 9, 0, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M")
    client.post(
        "/tasks",
        data={
            "title": "Weekly status update",
            "due_date": due,
            "recurrence_pattern": "weekly",
            "recurrence_interval": "1",
        },
    )
    original = db_session.query(Task).filter_by(title="Weekly status update").one()

    client.post(f"/tasks/{original.id}/complete")

    successor = (
        db_session.query(Task)
        .filter(Task.recurrence_series_id == original.recurrence_series_id, Task.id != original.id)
        .one()
    )
    assert successor.status == "open"
    assert successor.due_date == datetime(2026, 9, 27, 9, 0, tzinfo=UTC)
    assert successor.recurrence_active is True


def test_completing_paused_recurring_task_does_not_spawn_successor(client, db_session):
    from app.models import Task

    due = datetime(2026, 9, 20, 9, 0, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M")
    client.post(
        "/tasks",
        data={
            "title": "Monthly report",
            "due_date": due,
            "recurrence_pattern": "monthly",
            "recurrence_interval": "1",
        },
    )
    task = db_session.query(Task).filter_by(title="Monthly report").one()
    task.recurrence_active = False
    db_session.commit()

    client.post(f"/tasks/{task.id}/complete")

    successors = (
        db_session.query(Task)
        .filter(Task.recurrence_series_id == task.recurrence_series_id, Task.id != task.id)
        .all()
    )
    assert successors == []


def test_pause_recurrence_sets_inactive(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post(
        "/tasks",
        data={"title": "Daily standup", "due_date": due, "recurrence_pattern": "daily"},
    )
    task = db_session.query(Task).filter_by(title="Daily standup").one()

    response = client.patch(f"/tasks/{task.id}/recurrence", data={"active": "false"})
    assert response.status_code == 200

    db_session.refresh(task)
    assert task.recurrence_active is False


def test_pause_recurrence_on_non_recurring_task_returns_404(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "One-off review", "due_date": due})
    task = db_session.query(Task).filter_by(title="One-off review").one()

    response = client.patch(f"/tasks/{task.id}/recurrence", data={"active": "false"})
    assert response.status_code == 404
