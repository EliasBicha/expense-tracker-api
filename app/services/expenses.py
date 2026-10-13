import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Row, func, select
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.models import Category, Expense, User
from app.schemas.expenses import BudgetWarning, ExpenseCreate, ExpenseUpdate
from app.services.budget_alert import check_budget
from app.services.categories import get_usable_category


@dataclass(frozen=True)
class ExpenseFilters:
    """Optional, inclusive filters shared by listing and CSV export (EXP-08, EXP-12)."""

    date_from: date | None = None
    date_to: date | None = None
    category_id: uuid.UUID | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None


def _conditions(user: User, filters: ExpenseFilters) -> list:
    conditions = [Expense.user_id == user.id]  # ownership is always enforced (SEC-02)
    if filters.date_from is not None:
        conditions.append(Expense.expense_date >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(Expense.expense_date <= filters.date_to)
    if filters.category_id is not None:
        conditions.append(Expense.category_id == filters.category_id)
    if filters.min_amount is not None:
        conditions.append(Expense.amount >= filters.min_amount)
    if filters.max_amount is not None:
        conditions.append(Expense.amount <= filters.max_amount)
    return conditions


# Newest first; id as the final tie-breaker keeps pagination stable.
_ORDER = (Expense.expense_date.desc(), Expense.created_at.desc(), Expense.id.desc())


def get_expense(db: Session, user: User, expense_id: uuid.UUID) -> Expense:
    expense = db.scalar(
        select(Expense).where(Expense.id == expense_id, Expense.user_id == user.id)
    )
    if expense is None:
        raise NotFoundError("Expense not found", code="expense_not_found")
    return expense


def list_expenses(
    db: Session, user: User, filters: ExpenseFilters, limit: int, offset: int
) -> tuple[list[Expense], int]:
    conditions = _conditions(user, filters)
    total = db.scalar(select(func.count()).select_from(Expense).where(*conditions))
    items = db.scalars(
        select(Expense).where(*conditions).order_by(*_ORDER).limit(limit).offset(offset)
    )
    return list(items), total


def create_expense(
    db: Session, user: User, data: ExpenseCreate
) -> tuple[Expense, BudgetWarning | None]:
    category = get_usable_category(db, user, data.category_id)
    expense = Expense(
        user_id=user.id,
        category_id=category.id,
        amount=data.amount,
        currency=user.default_currency,  # server-controlled (D-05)
        expense_date=data.date,
        description=data.description,
        receipt_url=data.receipt_url,
    )
    db.add(expense)
    db.flush()  # make the new row visible to the budget SUM in this transaction
    warning = check_budget(db, user.id, category, expense.expense_date)
    db.commit()
    return expense, warning


def update_expense(
    db: Session, user: User, expense_id: uuid.UUID, data: ExpenseUpdate
) -> tuple[Expense, BudgetWarning | None]:
    expense = get_expense(db, user, expense_id)
    changes = data.model_dump(exclude_unset=True)
    if "category_id" in changes:
        category = get_usable_category(db, user, changes["category_id"])
    else:
        category = db.get(Category, expense.category_id)
    if "date" in changes:
        changes["expense_date"] = changes.pop("date")
    for field, value in changes.items():
        setattr(expense, field, value)
    db.flush()
    # Checked against the expense's category and month *after* the update (BAL-05, BAL-06).
    warning = check_budget(db, user.id, category, expense.expense_date)
    db.commit()
    return expense, warning


def delete_expense(db: Session, user: User, expense_id: uuid.UUID) -> None:
    expense = get_expense(db, user, expense_id)
    db.delete(expense)
    db.commit()


def iter_export_rows(db: Session, user: User, filters: ExpenseFilters) -> Iterator[Row]:
    """Rows for CSV export, fetched from the database in batches rather than all at once."""
    stmt = (
        select(
            Expense.id,
            Expense.expense_date,
            Expense.amount,
            Expense.currency,
            Category.name,
            Expense.description,
            Expense.receipt_url,
        )
        .join(Category, Category.id == Expense.category_id)
        .where(*_conditions(user, filters))
        .order_by(*_ORDER)
        .execution_options(yield_per=500)
    )
    yield from db.execute(stmt)
