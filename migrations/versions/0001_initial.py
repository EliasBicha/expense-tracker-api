"""Initial schema and system default categories.

Revision ID: 0001
Revises:
Create Date: 2026-10-12
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SYSTEM_CATEGORIES = [
    # (name, icon, color)
    ("Food", "food", "#FF7043"),
    ("Transport", "car", "#42A5F5"),
    ("Entertainment", "entertainment", "#AB47BC"),
    ("Shopping", "shopping", "#EC407A"),
    ("Bills", "bills", "#FFA726"),
    ("Health", "health", "#66BB6A"),
    ("Other", "other", "#78909C"),
]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("default_currency", sa.CHAR(3), nullable=False, server_default="USD"),
        *_timestamps(),
    )

    categories = op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("icon", sa.String(50), nullable=False),
        sa.Column("color", sa.CHAR(7), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.CheckConstraint("is_system = (user_id IS NULL)", name="ck_categories_system_owner"),
    )
    op.create_index(
        "uq_categories_user_name",
        "categories",
        ["user_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_categories_system_name",
        "categories",
        [sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )

    op.create_table(
        "expenses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "category_id", sa.Uuid(), sa.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("receipt_url", sa.String(2048), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
    )
    op.create_index("ix_expenses_user_date", "expenses", ["user_id", "expense_date"])
    op.create_index(
        "ix_expenses_user_category_date", "expenses", ["user_id", "category_id", "expense_date"]
    )

    op.create_table(
        "budgets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "category_id", sa.Uuid(), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("month", sa.SmallInteger(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("amount >= 0", name="ck_budgets_amount_non_negative"),
        sa.CheckConstraint("year BETWEEN 2000 AND 2100", name="ck_budgets_year_range"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_budgets_month_range"),
        sa.UniqueConstraint(
            "user_id", "category_id", "year", "month", name="uq_budgets_user_category_month"
        ),
    )

    op.bulk_insert(
        categories,
        [
            {"id": uuid.uuid4(), "name": name, "icon": icon, "color": color, "is_system": True, "user_id": None}
            for name, icon, color in SYSTEM_CATEGORIES
        ],
    )


def downgrade() -> None:
    op.drop_table("budgets")
    op.drop_table("expenses")
    op.drop_table("categories")
    op.drop_table("users")
