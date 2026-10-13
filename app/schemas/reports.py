import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

from app.schemas.common import Money, OutputModel

# Percentages are Decimal internally (rounded to 2 places) and JSON numbers on the wire.
Percent = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class CategoryTotal(OutputModel):
    category_id: uuid.UUID
    category_name: str
    total: Money


class MonthlySummary(OutputModel):
    year: int
    month: int
    currency: str
    total: Money
    by_category: list[CategoryTotal]


class TrendMonth(OutputModel):
    year: int
    month: int
    total: Money
    change_amount: Money | None
    change_percent: Percent | None


class SpendingTrend(OutputModel):
    currency: str
    months: list[TrendMonth]


class BudgetStatusItem(OutputModel):
    category_id: uuid.UUID
    category_name: str
    budget: Money
    spent: Money
    remaining: Money
    percent_used: Percent | None
    exceeded: bool
    has_limit: bool


class BudgetStatus(OutputModel):
    year: int
    month: int
    currency: str
    items: list[BudgetStatusItem]
