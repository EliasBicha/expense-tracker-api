import datetime as dt
import uuid
from typing import Annotated

from pydantic import AfterValidator, Field, HttpUrl, UrlConstraints, field_validator

from app import dates
from app.schemas.common import InputModel, Money, OutputModel, PositiveAmount, reject_null, trimmed

MIN_EXPENSE_DATE = dt.date(2000, 1, 1)
MAX_DAYS_IN_FUTURE = 7
MAX_RECEIPT_URL_LENGTH = 2048  # matches the VARCHAR(2048) column

Description = trimmed(max_length=500)


def check_receipt_url_length(value: str) -> str:
    """The URL parser can lengthen a URL while normalizing it (e.g. a space becomes %20),
    so the column limit is checked again on the final form that will be stored."""
    if len(value) > MAX_RECEIPT_URL_LENGTH:
        raise ValueError(f"URL should have at most {MAX_RECEIPT_URL_LENGTH} characters once normalized")
    return value


# http/https only (HttpUrl), stored as a plain string.
ReceiptUrl = Annotated[
    HttpUrl,
    UrlConstraints(max_length=MAX_RECEIPT_URL_LENGTH),
    AfterValidator(str),
    AfterValidator(check_receipt_url_length),
]


def check_expense_date(value: dt.date | None) -> dt.date | None:
    """EXP-04 / D-15: not before 2000-01-01, at most 7 days after today (UTC)."""
    if value is None:  # explicit null on PATCH is rejected separately by reject_null
        return value
    if value < MIN_EXPENSE_DATE:
        raise ValueError(f"date must be on or after {MIN_EXPENSE_DATE.isoformat()}")
    latest = dates.utc_today() + dt.timedelta(days=MAX_DAYS_IN_FUTURE)
    if value > latest:
        raise ValueError(
            f"date can be at most {MAX_DAYS_IN_FUTURE} days in the future "
            f"(latest allowed: {latest.isoformat()})"
        )
    return value


def empty_to_none(value: str | None) -> str | None:
    return value or None


# The JSON field is called `date` (as in the assignment); the class attribute is
# named `date` too, so the type is referenced as `dt.date` to avoid shadowing it.
class ExpenseCreate(InputModel):
    amount: PositiveAmount
    category_id: uuid.UUID
    date: dt.date
    description: Description | None = None
    receipt_url: ReceiptUrl | None = None

    _check_date = field_validator("date")(check_expense_date)
    _empty_description = field_validator("description")(empty_to_none)


class ExpenseUpdate(InputModel):
    amount: PositiveAmount | None = None
    category_id: uuid.UUID | None = None
    date: dt.date | None = None
    # These two are nullable: an explicit null clears them (EXP-10).
    description: Description | None = None
    receipt_url: ReceiptUrl | None = None

    _no_nulls = field_validator("amount", "category_id", "date")(reject_null)
    _check_date = field_validator("date")(check_expense_date)
    _empty_description = field_validator("description")(empty_to_none)


class ExpenseOut(OutputModel):
    id: uuid.UUID
    amount: Money
    currency: str
    category_id: uuid.UUID
    date: dt.date = Field(validation_alias="expense_date")
    description: str | None
    receipt_url: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class BudgetWarning(OutputModel):
    category: str
    budget: Money
    spent: Money
    exceeded_by: Money


class ExpenseWithWarning(OutputModel):
    """Response of both POST /expenses and PATCH /expenses/{id} (EXP-01, EXP-10)."""

    expense: ExpenseOut
    budget_warning: BudgetWarning | None


class ExpenseList(OutputModel):
    items: list[ExpenseOut]
    total: int
    limit: int
    offset: int
