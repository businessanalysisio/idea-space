from datetime import datetime, timezone

from app.models import ActivityLog, Task
from app.seed import seed_default_workspace
from app.services.activity import record_change

UTC = timezone.utc


def test_task_has_completion_note_field_defaulting_to_none(db_session):
    workspace, user = seed_default_workspace(db_session)
    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Draft outline",
        due_date=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
    )
    db_session.add(task)
    db_session.commit()

    assert task.completion_note is None


def test_record_change_writes_activity_log_row(db_session):
    workspace, user = seed_default_workspace(db_session)
    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Draft outline",
        due_date=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    record_change(db_session, task, "status", "open", "done")
    db_session.commit()

    entries = db_session.query(ActivityLog).filter_by(task_id=task.id).all()
    assert len(entries) == 1
    assert entries[0].field_name == "status"
    assert entries[0].old_value == "open"
    assert entries[0].new_value == "done"
    assert entries[0].workspace_id == workspace.id


def test_record_change_allows_null_old_value(db_session):
    workspace, user = seed_default_workspace(db_session)
    task = Task(
        workspace_id=workspace.id,
        owner_id=user.id,
        title="Draft outline",
        due_date=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    record_change(db_session, task, "due_date", None, "2026-09-22")
    db_session.commit()

    entry = db_session.query(ActivityLog).filter_by(task_id=task.id).one()
    assert entry.old_value is None
    assert entry.new_value == "2026-09-22"
