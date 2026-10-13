"""Calendar helpers. All "today" / "current month" logic goes through here (D-10)."""

from datetime import UTC, date, datetime


def utc_today() -> date:
    """Current UTC date. Tests monkeypatch this to freeze time."""
    return datetime.now(UTC).date()


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Return (year, month) moved by `delta` months (negative = backwards)."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_range(year: int, month: int) -> tuple[date, date]:
    """Half-open range [first day of month, first day of next month).

    Filtering with `expense_date >= start AND expense_date < end` lets
    PostgreSQL use the (user_id, ..., expense_date) indexes, unlike
    EXTRACT(MONTH FROM expense_date) = ?.
    """
    next_year, next_month = shift_month(year, month, 1)
    return date(year, month, 1), date(next_year, next_month, 1)
