from datetime import datetime, timezone

from app.services.recurrence import compute_next_due_date, project_occurrences

UTC = timezone.utc


def test_daily_recurrence_adds_interval_days():
    current = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    result = compute_next_due_date("daily", 1, None, current)
    assert result == datetime(2026, 9, 21, 9, 0, tzinfo=UTC)


def test_daily_recurrence_respects_interval():
    current = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    result = compute_next_due_date("daily", 3, None, current)
    assert result == datetime(2026, 9, 23, 9, 0, tzinfo=UTC)


def test_weekly_recurrence_without_days_adds_interval_weeks():
    current = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)  # Sunday
    result = compute_next_due_date("weekly", 1, None, current)
    assert result == datetime(2026, 9, 27, 9, 0, tzinfo=UTC)


def test_monthly_recurrence_adds_interval_months():
    current = datetime(2026, 1, 31, 9, 0, tzinfo=UTC)
    result = compute_next_due_date("monthly", 1, None, current)
    assert result == datetime(2026, 2, 28, 9, 0, tzinfo=UTC)


def test_custom_recurrence_finds_next_matching_weekday():
    # Sunday 2026-09-20, custom days = Mon(0), Wed(2), Fri(4)
    current = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    result = compute_next_due_date("custom", 1, "0,2,4", current)
    assert result == datetime(2026, 9, 21, 9, 0, tzinfo=UTC)  # next Monday


def test_custom_recurrence_without_days_returns_none():
    current = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    result = compute_next_due_date("custom", 1, None, current)
    assert result is None


def test_unknown_pattern_returns_none():
    current = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    result = compute_next_due_date("yearly", 1, None, current)
    assert result is None


def test_project_occurrences_within_range():
    from_due = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    range_start = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
    range_end = datetime(2026, 10, 11, 0, 0, tzinfo=UTC)

    occurrences = project_occurrences("weekly", 1, None, from_due, range_start, range_end)

    assert occurrences == [
        datetime(2026, 9, 27, 9, 0, tzinfo=UTC),
        datetime(2026, 10, 4, 9, 0, tzinfo=UTC),
    ]


def test_project_occurrences_returns_empty_for_non_recurring():
    from_due = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    range_start = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
    range_end = datetime(2026, 10, 11, 0, 0, tzinfo=UTC)

    occurrences = project_occurrences(None, 1, None, from_due, range_start, range_end)

    assert occurrences == []
