from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import ActivityLog, Task


def record_change(
    db: Session,
    task: Task,
    field_name: str,
    old_value: str | None,
    new_value: str,
) -> None:
    entry = ActivityLog(
        workspace_id=task.workspace_id,
        task_id=task.id,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        changed_at=datetime.now(timezone.utc),
    )
    db.add(entry)
