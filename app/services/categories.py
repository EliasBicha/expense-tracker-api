import uuid

from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ConflictError, ForbiddenError, NotFoundError
from app.models import Category, Expense, User
from app.schemas.categories import CategoryCreate, CategoryUpdate


def _visible_to(user: User):
    """System categories plus the user's own: the only categories a user may see or use."""
    return or_(Category.user_id.is_(None), Category.user_id == user.id)


def list_categories(db: Session, user: User) -> list[Category]:
    stmt = (
        select(Category)
        .where(_visible_to(user))
        .order_by(Category.is_system.desc(), func.lower(Category.name))
    )
    return list(db.scalars(stmt))


def get_usable_category(db: Session, user: User, category_id: uuid.UUID) -> Category:
    """A category the user may attach expenses/budgets to (EXP-02, BUD-02).

    Another user's category is reported exactly like a missing one (D-06).
    """
    category = db.scalar(select(Category).where(Category.id == category_id, _visible_to(user)))
    if category is None:
        raise NotFoundError("Category not found", code="category_not_found")
    return category


def _get_editable_category(db: Session, user: User, category_id: uuid.UUID) -> Category:
    category = get_usable_category(db, user, category_id)
    if category.is_system:
        raise ForbiddenError(
            "System categories can't be modified", code="system_category_readonly"
        )
    return category


def _ensure_name_available(
    db: Session, user: User, name: str, exclude_id: uuid.UUID | None = None
) -> None:
    """Case-insensitive check against the user's own and the system categories (CAT-03).

    lower() runs in PostgreSQL on both sides so the comparison matches the unique indexes.
    """
    condition = (func.lower(Category.name) == func.lower(name)) & _visible_to(user)
    if exclude_id is not None:
        condition &= Category.id != exclude_id
    if db.scalar(select(exists().where(condition))):
        raise ConflictError(
            f"A category named '{name}' already exists", code="category_name_taken"
        )


def _commit_name_change(db: Session, name: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        # Lost a race with a concurrent request creating the same name.
        db.rollback()
        raise ConflictError(
            f"A category named '{name}' already exists", code="category_name_taken"
        )


def create_category(db: Session, user: User, data: CategoryCreate) -> Category:
    _ensure_name_available(db, user, data.name)
    category = Category(
        name=data.name, icon=data.icon, color=data.color, is_system=False, user_id=user.id
    )
    db.add(category)
    _commit_name_change(db, data.name)
    return category


def update_category(
    db: Session, user: User, category_id: uuid.UUID, data: CategoryUpdate
) -> Category:
    category = _get_editable_category(db, user, category_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        _ensure_name_available(db, user, changes["name"], exclude_id=category.id)
    for field, value in changes.items():
        setattr(category, field, value)
    _commit_name_change(db, category.name)
    return category


def _expense_count(db: Session, user: User, category: Category) -> int:
    stmt = (
        select(func.count())
        .select_from(Expense)
        .where(Expense.user_id == user.id, Expense.category_id == category.id)
    )
    return db.scalar(stmt)


def _category_in_use(category: Category, count: int) -> ConflictError:
    return ConflictError(
        f"Category '{category.name}' has {count} expense(s). "
        "Move them to another category before deleting it.",
        code="category_in_use",
        details={"expense_count": count},
    )


def delete_category(db: Session, user: User, category_id: uuid.UUID) -> None:
    category = _get_editable_category(db, user, category_id)
    count = _expense_count(db, user, category)
    if count:
        raise _category_in_use(category, count)
    db.delete(category)  # budgets go with it via ON DELETE CASCADE (CAT-08)
    try:
        db.commit()
    except IntegrityError:
        # An expense was added between the count and the delete; the
        # ON DELETE RESTRICT foreign key stopped the delete.
        db.rollback()
        raise _category_in_use(category, _expense_count(db, user, category))
