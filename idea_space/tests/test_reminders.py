from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def _create_task_with_reminder(client, db_session, title, remind_offset_minutes):
    from app.models import Task, Reminder

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": title, "due_date": due})
    task = db_session.query(Task).filter_by(title=title).one()

    reminder = Reminder(
        task_id=task.id,
        remind_at=datetime.now(UTC) + timedelta(minutes=remind_offset_minutes),
    )
    db_session.add(reminder)
    db_session.commit()
    db_session.refresh(reminder)
    return task, reminder


def test_due_reminders_shows_past_due_reminder(client, db_session):
    _create_task_with_reminder(client, db_session, "Prep steering deck", -5)

    response = client.get("/reminders/due")
    assert response.status_code == 200
    assert b"Prep steering deck" in response.content


def test_due_reminders_excludes_future_reminder(client, db_session):
    _create_task_with_reminder(client, db_session, "Prep steering deck", 60)

    response = client.get("/reminders/due")
    assert b"Prep steering deck" not in response.content


def test_dismiss_reminder_removes_it_from_due_list(client, db_session):
    _, reminder = _create_task_with_reminder(client, db_session, "Prep steering deck", -5)

    response = client.post(f"/reminders/{reminder.id}/dismiss")
    assert response.status_code == 200
    assert b"Prep steering deck" not in response.content

    db_session.refresh(reminder)
    assert reminder.dismissed_at is not None


def test_snooze_reminder_hides_it_until_snooze_expires(client, db_session):
    _, reminder = _create_task_with_reminder(client, db_session, "Prep steering deck", -5)

    response = client.post(f"/reminders/{reminder.id}/snooze", data={"minutes": "15"})
    assert response.status_code == 200
    assert b"Prep steering deck" not in response.content

    db_session.refresh(reminder)
    # Normalize tzinfo since SQLite strips it
    if reminder.snoozed_until.tzinfo is None:
        reminder.snoozed_until = reminder.snoozed_until.replace(tzinfo=UTC)
    assert reminder.snoozed_until > datetime.now(UTC)


def test_snoozed_reminder_reappears_when_snooze_expires(client, db_session):
    from app.models import Reminder

    _, reminder = _create_task_with_reminder(client, db_session, "Prep steering deck", -5)

    # Snooze it
    client.post(f"/reminders/{reminder.id}/snooze", data={"minutes": "15"})

    # Verify it's hidden while snoozed
    response = client.get("/reminders/due")
    assert b"Prep steering deck" not in response.content

    # Manually set snoozed_until to the past so it expires
    db_session.refresh(reminder)
    reminder.snoozed_until = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    # Now it should reappear
    response = client.get("/reminders/due")
    assert response.status_code == 200
    assert b"Prep steering deck" in response.content


def test_completed_task_suppresses_its_reminder(client, db_session):
    task, _ = _create_task_with_reminder(client, db_session, "Prep steering deck", -5)

    client.post(f"/tasks/{task.id}/complete")

    response = client.get("/reminders/due")
    assert b"Prep steering deck" not in response.content


def test_due_reminders_excludes_archived_task(client, db_session):
    from app.models import Reminder, Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Old task", "due_date": due})
    task = db_session.query(Task).filter_by(title="Old task").one()

    reminder = Reminder(task_id=task.id, remind_at=datetime.now(UTC) - timedelta(minutes=5))
    db_session.add(reminder)
    db_session.commit()

    client.post(f"/tasks/{task.id}/complete")
    client.post(f"/tasks/{task.id}/archive")

    response = client.get("/reminders/due")
    assert b"Old task" not in response.content
