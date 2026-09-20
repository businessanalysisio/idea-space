from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def test_get_tasks_returns_empty_list_page(client):
    response = client.get("/tasks")
    assert response.status_code == 200
    assert 'class="metrics-row"' in response.text
    assert 'data-board-column="now"' in response.text


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


def test_overdue_task_lands_in_now_column(client):
    # Redesign note: the board no longer marks overdue tasks with a
    # dedicated CSS class (`.task--overdue` only survives in the archived
    # list's `_row.html`); instead overdue tasks simply surface in the NOW
    # column since their due_date is in the past (before today's end).
    overdue_due = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Send follow-up email", "due_date": overdue_due})

    response = client.get("/tasks")
    body = response.text
    now_idx = body.index('data-board-column="now"')
    next_idx = body.index('data-board-column="next"')
    assert "Send follow-up email" in body[now_idx:next_idx]


def test_complete_non_recurring_task_moves_it_from_open_columns_to_done(client, db_session):
    # Redesign note: the returned fragment is now the whole board (#task-board),
    # which includes a DONE column showing recently completed tasks — so the
    # completed task is expected to appear there, just no longer in NOW/NEXT.
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "One-off review", "due_date": due})
    task = db_session.query(Task).filter_by(title="One-off review").one()

    response = client.post(f"/tasks/{task.id}/complete")
    assert response.status_code == 200
    body = response.text
    now_idx = body.index('data-board-column="now"')
    next_idx = body.index('data-board-column="next"')
    done_idx = body.index('data-board-column="done"')
    assert "One-off review" not in body[now_idx:next_idx]
    assert "One-off review" not in body[next_idx:done_idx]
    assert "One-off review" in body[done_idx:]

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


def test_completing_recurring_task_carries_labels_to_successor(client, db_session):
    from app.models import Label, Task

    due = datetime(2026, 9, 20, 9, 0, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M")
    client.post(
        "/tasks",
        data={
            "title": "Weekly review",
            "due_date": due,
            "recurrence_pattern": "weekly",
            "recurrence_interval": "1",
        },
    )
    client.post("/labels", data={"name": "Focus", "color": "#22c55e"})

    original = db_session.query(Task).filter_by(title="Weekly review").one()
    label = db_session.query(Label).filter_by(name="Focus").one()
    client.post(f"/tasks/{original.id}/labels", data={"label_id": label.id})

    client.post(f"/tasks/{original.id}/complete")

    successor = (
        db_session.query(Task)
        .filter(Task.recurrence_series_id == original.recurrence_series_id, Task.id != original.id)
        .one()
    )
    assert [l.name for l in successor.labels] == ["Focus"]


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


def test_reschedule_moves_task_to_new_date(client, db_session):
    from app.models import Task

    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    client.post(
        "/tasks",
        data={"title": "Stakeholder sync", "due_date": due.strftime("%Y-%m-%dT%H:%M")},
    )
    task = db_session.query(Task).filter_by(title="Stakeholder sync").one()

    response = client.patch(f"/tasks/{task.id}/reschedule", data={"due_date": "2026-09-24"})
    assert response.status_code == 200

    db_session.refresh(task)
    assert task.due_date.date().isoformat() == "2026-09-24"
    assert task.due_date.time().isoformat() == "10:00:00"


def test_reschedule_non_open_task_returns_404(client, db_session):
    from app.models import Task

    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    client.post(
        "/tasks",
        data={"title": "Completed task", "due_date": due.strftime("%Y-%m-%dT%H:%M")},
    )
    task = db_session.query(Task).filter_by(title="Completed task").one()
    task.status = "done"
    db_session.commit()

    response = client.patch(f"/tasks/{task.id}/reschedule", data={"due_date": "2026-09-24"})
    assert response.status_code == 404


def test_reschedule_unknown_task_returns_404(client):
    response = client.patch("/tasks/999/reschedule", data={"due_date": "2026-09-24"})
    assert response.status_code == 404


def test_filter_tasks_by_label(client, db_session):
    from app.models import Label, Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    client.post("/tasks", data={"title": "Review budget", "due_date": due})
    client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})

    outline = db_session.query(Task).filter_by(title="Draft outline").one()
    label = db_session.query(Label).filter_by(name="Urgent").one()
    client.post(f"/tasks/{outline.id}/labels", data={"label_id": label.id})

    response = client.get(f"/tasks?labels={label.id}")
    assert b"Draft outline" in response.content
    assert b"Review budget" not in response.content


def test_filter_tasks_by_multiple_labels_is_or_matched(client, db_session):
    from app.models import Label, Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    client.post("/tasks", data={"title": "Review budget", "due_date": due})
    client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})
    client.post("/labels", data={"name": "Finance", "color": "#3b82f6"})

    outline = db_session.query(Task).filter_by(title="Draft outline").one()
    budget = db_session.query(Task).filter_by(title="Review budget").one()
    urgent = db_session.query(Label).filter_by(name="Urgent").one()
    finance = db_session.query(Label).filter_by(name="Finance").one()
    client.post(f"/tasks/{outline.id}/labels", data={"label_id": urgent.id})
    client.post(f"/tasks/{budget.id}/labels", data={"label_id": finance.id})

    response = client.get(f"/tasks?labels={urgent.id},{finance.id}")
    assert b"Draft outline" in response.content
    assert b"Review budget" in response.content


def test_clear_filters_link_present(client):
    response = client.get("/tasks?labels=1&status=open")
    assert b'href="/tasks"' in response.content


def test_complete_task_with_note_stores_it(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()

    client.post(f"/tasks/{task.id}/complete", data={"completion_note": "Sent to stakeholders"})

    db_session.refresh(task)
    assert task.completion_note == "Sent to stakeholders"


def test_complete_task_without_note_leaves_it_none(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()

    client.post(f"/tasks/{task.id}/complete")

    db_session.refresh(task)
    assert task.completion_note is None


def test_complete_task_with_empty_note_normalizes_to_none(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()

    client.post(f"/tasks/{task.id}/complete", data={"completion_note": ""})

    db_session.refresh(task)
    assert task.completion_note is None


def test_complete_task_logs_status_change(client, db_session):
    from app.models import ActivityLog, Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()

    client.post(f"/tasks/{task.id}/complete")

    entry = db_session.query(ActivityLog).filter_by(task_id=task.id, field_name="status").one()
    assert entry.old_value == "open"
    assert entry.new_value == "done"


def test_reschedule_logs_due_date_change(client, db_session):
    from app.models import ActivityLog, Task

    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    client.post(
        "/tasks",
        data={"title": "Stakeholder sync", "due_date": due.strftime("%Y-%m-%dT%H:%M")},
    )
    task = db_session.query(Task).filter_by(title="Stakeholder sync").one()

    client.patch(f"/tasks/{task.id}/reschedule", data={"due_date": "2026-09-24"})

    entry = db_session.query(ActivityLog).filter_by(task_id=task.id, field_name="due_date").one()
    assert entry.old_value == "2026-09-22"
    assert entry.new_value == "2026-09-24"


def test_archive_requires_done_status(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()

    response = client.post(f"/tasks/{task.id}/archive")
    assert response.status_code == 404


def test_archive_moves_task_from_done_to_archived_view(client, db_session):
    from app.models import ActivityLog, Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()
    client.post(f"/tasks/{task.id}/complete")

    response = client.post(f"/tasks/{task.id}/archive")
    assert response.status_code == 200
    assert b"Draft outline" not in response.content

    db_session.refresh(task)
    assert task.status == "archived"

    entry = (
        db_session.query(ActivityLog)
        .filter_by(task_id=task.id, field_name="status", new_value="archived")
        .one()
    )
    assert entry.old_value == "done"

    done_view = client.get("/tasks?status=done")
    assert b"Draft outline" not in done_view.content

    archived_view = client.get("/tasks?status=archived")
    assert b"Draft outline" in archived_view.content


def test_list_tasks_rejects_invalid_status(client):
    response = client.get("/tasks?status=banana")
    assert response.status_code == 400


def test_history_lists_entries_newest_first_and_includes_note(client, db_session):
    from app.models import Task

    due = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    client.post(
        "/tasks",
        data={"title": "Stakeholder sync", "due_date": due.strftime("%Y-%m-%dT%H:%M")},
    )
    task = db_session.query(Task).filter_by(title="Stakeholder sync").one()

    client.patch(f"/tasks/{task.id}/reschedule", data={"due_date": "2026-09-24"})
    client.post(f"/tasks/{task.id}/complete", data={"completion_note": "Done early"})

    response = client.get(f"/tasks/{task.id}/history")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Done early" in body
    assert "due_date" in body
    assert "status" in body
    assert body.index("status") < body.index("due_date")


def test_history_unknown_task_returns_404(client):
    response = client.get("/tasks/999/history")
    assert response.status_code == 404


def test_complete_task_requires_open_status(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()
    client.post(f"/tasks/{task.id}/complete")  # now done

    response = client.post(f"/tasks/{task.id}/complete")
    assert response.status_code == 404


def test_tasks_page_shows_enabled_checkbox_only_on_open_tasks(client, db_session):
    # Redesign note: the board card no longer has an inline completion-note
    # text input (completion_note is still accepted by the API — see
    # test_complete_task_with_note_stores_it — just not surfaced in this
    # quick-capture-first UI). The open/done distinction now shows up as an
    # enabled vs. checked-and-disabled checkbox instead.
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()

    response = client.get("/tasks")
    assert 'class="task-card-checkbox" onclick=' in response.text

    client.post(f"/tasks/{task.id}/complete")

    response = client.get("/tasks")
    assert 'class="task-card-checkbox" checked disabled' in response.text


def test_recurring_successor_does_not_inherit_completion_note(client, db_session):
    from app.models import Task

    due = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    client.post(
        "/tasks",
        data={
            "title": "Weekly review",
            "due_date": due.strftime("%Y-%m-%dT%H:%M"),
            "recurrence_pattern": "weekly",
            "recurrence_interval": "1",
        },
    )
    original = db_session.query(Task).filter_by(title="Weekly review").one()

    client.post(f"/tasks/{original.id}/complete", data={"completion_note": "Sent to stakeholders"})

    successor = (
        db_session.query(Task)
        .filter(Task.recurrence_series_id == original.recurrence_series_id, Task.id != original.id)
        .one()
    )
    assert successor.completion_note is None


def test_history_empty_for_task_with_no_changes(client, db_session):
    from app.models import Task

    due = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/tasks", data={"title": "Draft outline", "due_date": due})
    task = db_session.query(Task).filter_by(title="Draft outline").one()

    response = client.get(f"/tasks/{task.id}/history")
    assert response.status_code == 200
    assert b"No changes recorded yet" in response.content


def test_tasks_page_shows_metrics_row(client):
    due_today = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Today task", "due_date": due_today})

    response = client.get("/tasks")
    assert response.status_code == 200
    body = response.text
    assert 'class="metrics-row"' in body
    assert "OPEN" in body
    assert "IN FOCUS" in body
    assert "COMPLETED" in body
    assert "BLOCKED" in body


def test_task_due_today_lands_in_now_column_and_future_task_in_next(client):
    due_today = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    due_future = (datetime.now(UTC) + timedelta(days=5)).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Now task", "due_date": due_today})
    client.post("/tasks", data={"title": "Next task", "due_date": due_future})

    response = client.get("/tasks")
    body = response.text
    now_idx = body.index('data-board-column="now"')
    next_idx = body.index('data-board-column="next"')
    now_section = body[now_idx:next_idx]
    next_section = body[next_idx:]

    assert "Now task" in now_section
    assert "Next task" not in now_section
    assert "Next task" in next_section


def test_completed_task_lands_in_done_column(client, db_session):
    from app.models import Task

    due_today = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Finish me", "due_date": due_today})
    task = db_session.query(Task).filter_by(title="Finish me").one()
    client.post(f"/tasks/{task.id}/complete")

    response = client.get("/tasks")
    body = response.text
    done_idx = body.index('data-board-column="done"')
    assert "Finish me" in body[done_idx:]


def test_block_toggle_flips_and_is_reversible(client, db_session):
    from app.models import Task

    due_today = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Blockable", "due_date": due_today})
    task = db_session.query(Task).filter_by(title="Blockable").one()

    first = client.patch(f"/tasks/{task.id}/block")
    assert first.status_code == 200
    assert "task-card-blocked-badge" in first.text
    db_session.refresh(task)
    assert task.blocked is True

    second = client.patch(f"/tasks/{task.id}/block")
    assert second.status_code == 200
    db_session.refresh(task)
    assert task.blocked is False


def test_block_nonexistent_task_returns_404(client):
    response = client.patch("/tasks/999999/block")
    assert response.status_code == 404


def test_block_archived_task_returns_404(client, db_session):
    from app.models import Task

    due_today = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "To archive", "due_date": due_today})
    task = db_session.query(Task).filter_by(title="To archive").one()
    client.post(f"/tasks/{task.id}/complete")
    client.post(f"/tasks/{task.id}/archive")

    response = client.patch(f"/tasks/{task.id}/block")
    assert response.status_code == 404


def test_full_task_form_with_recurrence_and_reminder_fields_is_reachable(client):
    response = client.get("/tasks")
    assert response.status_code == 200
    body = response.text
    assert 'name="recurrence_pattern"' in body
    assert 'name="remind_at"' in body


def test_board_view_still_filters_by_label(client, db_session):
    # Regression check: the pre-redesign `/tasks?labels=X` filter (covered by
    # test_filter_tasks_by_label / test_filter_tasks_by_multiple_labels_is_or_matched
    # earlier in this file) must keep working now that the default view is
    # the NOW/NEXT/DONE board instead of a flat list.
    from app.models import Label, Task

    due_today = datetime.now(UTC).strftime("%Y-%m-%dT12:00")
    client.post("/tasks", data={"title": "Tagged task", "due_date": due_today})
    client.post("/tasks", data={"title": "Untagged task", "due_date": due_today})
    client.post("/labels", data={"name": "Urgent", "color": "#ef4444"})
    label = db_session.query(Label).filter_by(name="Urgent").one()
    tagged = db_session.query(Task).filter_by(title="Tagged task").one()
    client.post(f"/tasks/{tagged.id}/labels", data={"label_id": label.id})

    response = client.get(f"/tasks?labels={label.id}")
    assert response.status_code == 200
    assert "Tagged task" in response.text
    assert "Untagged task" not in response.text
