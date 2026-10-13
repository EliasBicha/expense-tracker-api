import uuid

from pydantic import Field

from app.schemas.common import InputModel, Money, NonNegativeAmount, OutputModel


class BudgetUpsert(InputModel):
    category_id: uuid.UUID
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    amount: NonNegativeAmount


class BudgetOut(OutputModel):
    id: uuid.UUID
    category_id: uuid.UUID
    category_name: str
    year: int
    month: int
    amount: Money
