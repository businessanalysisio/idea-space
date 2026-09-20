from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def test_calendar_week_shows_real_task_on_its_day(client):
    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)  # Tuesday
    client.post(
        "/tasks",
        data={"title": "Stakeholder sync", "due_date": due.strftime("%Y-%m-%dT%H:%M")},
    )

    response = client.get("/calendar?start=2026-09-21")
    assert response.status_code == 200
    assert b"Stakeholder sync" in response.content


def test_calendar_week_shows_virtual_projected_occurrence(client):
    due = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)  # Sunday, week 1
    client.post(
        "/tasks",
        data={
            "title": "Weekly status update",
            "due_date": due.strftime("%Y-%m-%dT%H:%M"),
            "recurrence_pattern": "weekly",
            "recurrence_interval": "1",
        },
    )

    # Week of 2026-09-27 has no real row yet, only the virtual projection.
    response = client.get("/calendar?start=2026-09-21")
    assert b"task--virtual" in response.content
    assert b"Weekly status update" in response.content


def test_calendar_week_lists_overdue_tasks_from_before_the_range(client):
    overdue_due = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    client.post(
        "/tasks",
        data={"title": "Send follow-up email", "due_date": overdue_due.strftime("%Y-%m-%dT%H:%M")},
    )

    response = client.get("/calendar?start=2026-09-21")
    assert b"Send follow-up email" in response.content
    assert b"calendar-overdue" in response.content


def test_calendar_excludes_archived_tasks(client, db_session):
    from app.models import Task

    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    client.post("/tasks", data={"title": "Old task", "due_date": due.strftime("%Y-%m-%dT%H:%M")})
    task = db_session.query(Task).filter_by(title="Old task").one()
    client.post(f"/tasks/{task.id}/complete")
    client.post(f"/tasks/{task.id}/archive")

    response = client.get("/calendar?start=2026-09-21")
    assert b"Old task" not in response.content
