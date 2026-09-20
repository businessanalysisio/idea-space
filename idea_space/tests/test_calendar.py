from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def test_calendar_week_shows_real_task_on_its_day(client):
    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)  # Tuesday
    client.post(
        "/tasks",
        data={"title": "Stakeholder sync", "due_date": due.strftime("%Y-%m-%dT%H:%M")},
    )

    response = client.get("/calendar?view=week&start=2026-09-21")
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
    response = client.get("/calendar?view=week&start=2026-09-21")
    assert b"task--virtual" in response.content
    assert b"Weekly status update" in response.content


def test_calendar_week_lists_overdue_tasks_from_before_the_range(client):
    overdue_due = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    client.post(
        "/tasks",
        data={"title": "Send follow-up email", "due_date": overdue_due.strftime("%Y-%m-%dT%H:%M")},
    )

    response = client.get("/calendar?view=week&start=2026-09-21")
    assert b"Send follow-up email" in response.content
    assert b"calendar-overdue" in response.content


def test_calendar_excludes_archived_tasks(client, db_session):
    from app.models import Task

    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    client.post("/tasks", data={"title": "Old task", "due_date": due.strftime("%Y-%m-%dT%H:%M")})
    task = db_session.query(Task).filter_by(title="Old task").one()
    client.post(f"/tasks/{task.id}/complete")
    client.post(f"/tasks/{task.id}/archive")

    response = client.get("/calendar?view=week&start=2026-09-21")
    assert b"Old task" not in response.content


def test_calendar_defaults_to_month_view(client):
    response = client.get("/calendar")
    assert response.status_code == 200
    assert 'data-view="month"' in response.text


def test_calendar_month_view_pads_to_full_weeks(client):
    # September 2026 starts on a Tuesday and has 30 days -> 5 rows of 7 = 35 cells.
    response = client.get("/calendar?view=month&month=2026-09")
    assert response.status_code == 200
    assert response.text.count('class="calendar-day') == 35


def test_calendar_week_view_still_works(client):
    response = client.get("/calendar?view=week")
    assert response.status_code == 200
    assert 'data-view="week"' in response.text


def test_calendar_agenda_view_shows_only_next_14_days(client):
    within_range = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%dT12:00")
    out_of_range = (datetime.now(UTC) + timedelta(days=20)).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Soon task", "due_date": within_range})
    client.post("/tasks", data={"title": "Far task", "due_date": out_of_range})

    response = client.get("/calendar?view=agenda")
    assert response.status_code == 200
    assert 'data-view="agenda"' in response.text
    assert "Soon task" in response.text
    assert "Far task" not in response.text


def test_calendar_invalid_view_returns_400(client):
    response = client.get("/calendar?view=bogus")
    assert response.status_code == 400


def test_reschedule_returns_matching_fragment_for_requested_view(client, db_session):
    from app.models import Task

    due_date = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Move me", "due_date": due_date})
    task = db_session.query(Task).filter_by(title="Move me").one()

    new_date = (datetime.now(UTC) + timedelta(days=2)).strftime("%Y-%m-%d")
    response = client.patch(
        f"/tasks/{task.id}/reschedule",
        data={"due_date": new_date, "view": "agenda"},
    )
    assert response.status_code == 200
    assert 'id="calendar-content"' in response.text
    assert 'data-view="agenda"' in response.text
