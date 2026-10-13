"""Budget alert shared by expense creation and update (BAL-01..06)."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dates import month_range
from app.models import Budget, Category, Expense
from app.schemas.expenses import BudgetWarning


def month_spent(
    db: Session, user_id: uuid.UUID, category_id: uuid.UUID, year: int, month: int
) -> Decimal:
    start, end = month_range(year, month)
    spending_query = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.user_id == user_id,
        Expense.category_id == category_id,
        Expense.expense_date >= start,
        Expense.expense_date < end,
    )
    return db.scalar(spending_query)


def check_budget(
    db: Session, user_id: uuid.UUID, category: Category, expense_date: date
) -> BudgetWarning | None:
    """Return a warning if the category's budget for the month of `expense_date` is exceeded.

    Must be called after the expense change is flushed: `spent` is a fresh SUM over the
    stored rows, so it is correct for creates, amount changes and moves alike, with no
    incremental bookkeeping (BAL-01, BAL-06).
    """
    year, month = expense_date.year, expense_date.month
    budget = db.scalar(
        select(Budget.amount).where(
            Budget.user_id == user_id,
            Budget.category_id == category.id,
            Budget.year == year,
            Budget.month == month,
        )
    )
    # No budget, or a zero budget ("track but don't limit", D-04): never warn.
    if budget is None or budget == 0:
        return None
    spent = month_spent(db, user_id, category.id, year, month)
    if spent <= budget:  # exceeding means strictly greater (BAL-02, BAL-03)
        return None
    return BudgetWarning(
        category=category.name, budget=budget, spent=spent, exceeded_by=spent - budget
    )
