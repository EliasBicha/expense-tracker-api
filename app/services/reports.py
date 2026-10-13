"""Reports (RPT-01..04). Aggregation happens in SQL; Python only shapes the
handful of grouped rows (one per category or per month).

All amounts are in the user's default currency: D-05 guarantees every expense
was recorded in it, so no conversion or currency filtering is needed.
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app import dates
from app.models import Budget, Category, Expense, User
from app.schemas.reports import (
    BudgetStatus,
    BudgetStatusItem,
    CategoryTotal,
    MonthlySummary,
    SpendingTrend,
    TrendMonth,
)

ZERO = Decimal("0")
CENT = Decimal("0.01")


def _percent(part: Decimal, whole: Decimal) -> Decimal:
    return (part / whole * 100).quantize(CENT, rounding=ROUND_HALF_UP)


def monthly_summary(db: Session, user: User, year: int, month: int) -> MonthlySummary:
    start, end = dates.month_range(year, month)
    total = func.sum(Expense.amount).label("total")
    rows = db.execute(
        select(Category.id, Category.name, total)
        .select_from(Expense)
        .join(Category, Category.id == Expense.category_id)
        .where(
            Expense.user_id == user.id,
            Expense.expense_date >= start,
            Expense.expense_date < end,
        )
        .group_by(Category.id, Category.name)
        .order_by(total.desc(), Category.name)
    ).all()
    return MonthlySummary(
        year=year,
        month=month,
        currency=user.default_currency,
        total=sum((row.total for row in rows), ZERO),
        by_category=[
            CategoryTotal(category_id=row.id, category_name=row.name, total=row.total)
            for row in rows
        ],
    )


def spending_trend(db: Session, user: User, months: int) -> SpendingTrend:
    today = dates.utc_today()
    first_year, first_month = dates.shift_month(today.year, today.month, -(months - 1))
    start, _ = dates.month_range(first_year, first_month)
    _, end = dates.month_range(today.year, today.month)

    year_col = extract("year", Expense.expense_date).label("year")
    month_col = extract("month", Expense.expense_date).label("month")
    rows = db.execute(
        select(year_col, month_col, func.sum(Expense.amount).label("total"))
        .where(
            Expense.user_id == user.id,
            Expense.expense_date >= start,
            Expense.expense_date < end,
        )
        .group_by(year_col, month_col)
    ).all()
    totals = {(int(row.year), int(row.month)): row.total for row in rows}

    result: list[TrendMonth] = []
    previous: Decimal | None = None
    for offset in range(months):
        year, month = dates.shift_month(first_year, first_month, offset)
        total = totals.get((year, month), ZERO)  # months without spending count as 0
        if previous is None:
            change_amount = change_percent = None
        else:
            change_amount = total - previous
            change_percent = _percent(change_amount, previous) if previous else None
        result.append(
            TrendMonth(
                year=year,
                month=month,
                total=total,
                change_amount=change_amount,
                change_percent=change_percent,
            )
        )
        previous = total
    return SpendingTrend(currency=user.default_currency, months=result)


def budget_status(db: Session, user: User, year: int, month: int) -> BudgetStatus:
    start, end = dates.month_range(year, month)
    spent_by_category = (
        select(Expense.category_id, func.sum(Expense.amount).label("spent"))
        .where(
            Expense.user_id == user.id,
            Expense.expense_date >= start,
            Expense.expense_date < end,
        )
        .group_by(Expense.category_id)
        .subquery()
    )
    rows = db.execute(
        select(
            Budget.category_id,
            Category.name,
            Budget.amount,
            func.coalesce(spent_by_category.c.spent, 0).label("spent"),
        )
        .join(Category, Category.id == Budget.category_id)
        .outerjoin(spent_by_category, spent_by_category.c.category_id == Budget.category_id)
        .where(Budget.user_id == user.id, Budget.year == year, Budget.month == month)
        .order_by(func.lower(Category.name))
    ).all()

    items = []
    for row in rows:
        has_limit = row.amount > 0  # a zero budget tracks without limiting (D-04)
        items.append(
            BudgetStatusItem(
                category_id=row.category_id,
                category_name=row.name,
                budget=row.amount,
                spent=row.spent,
                remaining=row.amount - row.spent,
                percent_used=_percent(row.spent, row.amount) if has_limit else None,
                exceeded=has_limit and row.spent > row.amount,
                has_limit=has_limit,
            )
        )
    return BudgetStatus(
        year=year, month=month, currency=user.default_currency, items=items
    )
