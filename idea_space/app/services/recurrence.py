from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

MAX_LOOKAHEAD_DAYS = 366


def compute_next_due_date(
    pattern: str | None,
    interval: int,
    days_of_week: str | None,
    current_due_date: datetime,
) -> datetime | None:
    if pattern == "daily":
        return current_due_date + timedelta(days=interval)

    if pattern == "weekly":
        if not days_of_week:
            return current_due_date + timedelta(weeks=interval)
        return _next_matching_weekday(current_due_date, days_of_week, interval)

    if pattern == "monthly":
        return current_due_date + relativedelta(months=interval)

    if pattern == "custom":
        if not days_of_week:
            return None
        return _next_matching_weekday(current_due_date, days_of_week, interval)

    return None


def _next_matching_weekday(
    current_due_date: datetime, days_of_week: str, interval: int
) -> datetime | None:
    allowed = {int(d) for d in days_of_week.split(",")}
    for offset in range(1, 7 * interval + 1):
        candidate = current_due_date + timedelta(days=offset)
        if candidate.weekday() in allowed:
            return candidate
    return None


def project_occurrences(
    pattern: str | None,
    interval: int,
    days_of_week: str | None,
    from_due_date: datetime,
    range_start: datetime,
    range_end: datetime,
) -> list[datetime]:
    if pattern is None:
        return []

    occurrences: list[datetime] = []
    current = from_due_date
    steps = 0
    while steps < MAX_LOOKAHEAD_DAYS:
        steps += 1
        next_date = compute_next_due_date(pattern, interval, days_of_week, current)
        if next_date is None or next_date > range_end:
            break
        if next_date >= range_start:
            occurrences.append(next_date)
        current = next_date

    return occurrences
