"""SQLAlchemy models. The schema itself is created by Alembic (migrations/), not by create_all.

Constraints and indexes are declared here as well so the models document the schema;
migrations/versions/0001_initial.py must stay in sync with this file.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, server_default=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    default_currency: Mapped[str] = mapped_column(CHAR(3), server_default="USD")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50))
    icon: Mapped[str] = mapped_column(String(50))
    color: Mapped[str] = mapped_column(CHAR(7))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    # NULL for system categories, owner's id for custom ones.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("is_system = (user_id IS NULL)", name="ck_categories_system_owner"),
        # Case-insensitive uniqueness per owner, and among system categories (D-07).
        Index(
            "uq_categories_user_name",
            "user_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_categories_system_name",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("user_id IS NULL"),
        ),
    )


class Expense(TimestampMixin, Base):
    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # RESTRICT: the database itself refuses to delete a category that still has expenses.
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(CHAR(3))
    expense_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
        Index("ix_expenses_user_date", "user_id", "expense_date"),
        Index("ix_expenses_user_category_date", "user_id", "category_id", "expense_date"),
    )


class Budget(TimestampMixin, Base):
    __tablename__ = "budgets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # CASCADE: deleting an (unused) category also removes its budgets (CAT-08).
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    year: Mapped[int] = mapped_column(SmallInteger)
    month: Mapped[int] = mapped_column(SmallInteger)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_budgets_amount_non_negative"),
        CheckConstraint("year BETWEEN 2000 AND 2100", name="ck_budgets_year_range"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_budgets_month_range"),
        UniqueConstraint("user_id", "category_id", "year", "month", name="uq_budgets_user_category_month"),
    )
