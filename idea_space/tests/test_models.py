from datetime import datetime, timezone

from app.models import Task, Label, Reminder
from app.seed import seed_default_workspace


def test_seed_is_idempotent(db_session):
    workspace1, user1 = seed_default_workspace(db_session)
    workspace2, user2 = seed_default_workspace(db_session)

    assert workspace1.id == workspace2.id
    assert user1.id == user2.id
    assert workspace1.name == "My Workspace"


def test_task_defaults_to_open_status(db_session):
    workspace, user = seed_default_workspace(db_session)
    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Draft requirements outline",
        due_date=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add(task)
    db_session.commit()

    assert task.id is not None
    assert task.status == "open"
    assert task.recurrence_active is False
    assert task.recurrence_series_id is None


def test_task_label_many_to_many(db_session):
    workspace, user = seed_default_workspace(db_session)
    label = Label(workspace_id=workspace.id, name="Urgent", color="#ef4444")
    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Review stakeholder list",
        due_date=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
    )
    task.labels.append(label)
    db_session.add(task)
    db_session.commit()

    assert task.labels[0].name == "Urgent"


def test_reminder_links_to_task(db_session):
    workspace, user = seed_default_workspace(db_session)
    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Prep steering deck",
        due_date=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add(task)
    db_session.commit()

    reminder = Reminder(
        task_id=task.id,
        remind_at=datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc),
    )
    db_session.add(reminder)
    db_session.commit()

    assert reminder.id is not None
    assert reminder.dismissed_at is None
    assert reminder.snoozed_until is None
