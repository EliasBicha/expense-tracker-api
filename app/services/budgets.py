import uuid

from sqlalchemy import Row, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.models import Budget, Category, User
from app.schemas.budgets import BudgetUpsert
from app.services.categories import get_usable_category


def _find(db: Session, user: User, data: BudgetUpsert) -> Budget | None:
    return db.scalar(
        select(Budget).where(
            Budget.user_id == user.id,
            Budget.category_id == data.category_id,
            Budget.year == data.year,
            Budget.month == data.month,
        )
    )


def upsert_budget(db: Session, user: User, data: BudgetUpsert) -> tuple[Budget, Category, bool]:
    """Create or update the budget for (user, category, year, month).

    Returns (budget, category, created).
    """
    category = get_usable_category(db, user, data.category_id)
    budget = _find(db, user, data)
    if budget is not None:
        budget.amount = data.amount
        db.commit()
        return budget, category, False

    budget = Budget(
        user_id=user.id,
        category_id=category.id,
        year=data.year,
        month=data.month,
        amount=data.amount,
    )
    db.add(budget)
    try:
        db.commit()
        return budget, category, True
    except IntegrityError:
        # A concurrent request created the same budget first: update that one instead.
        db.rollback()
        budget = _find(db, user, data)
        if budget is None:  # the failure was something else; don't hide it
            raise
        budget.amount = data.amount
        db.commit()
        return budget, category, False


def list_budgets(
    db: Session, user: User, year: int | None, month: int | None
) -> list[Row]:
    stmt = (
        select(Budget, Category.name.label("category_name"))
        .join(Category, Category.id == Budget.category_id)
        .where(Budget.user_id == user.id)
        .order_by(Budget.year.desc(), Budget.month.desc(), func.lower(Category.name))
    )
    if year is not None:
        stmt = stmt.where(Budget.year == year)
    if month is not None:
        stmt = stmt.where(Budget.month == month)
    return list(db.execute(stmt))


def delete_budget(db: Session, user: User, budget_id: uuid.UUID) -> None:
    budget = db.scalar(select(Budget).where(Budget.id == budget_id, Budget.user_id == user.id))
    if budget is None:
        raise NotFoundError("Budget not found", code="budget_not_found")
    db.delete(budget)
    db.commit()
