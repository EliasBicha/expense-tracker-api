from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints

MAX_AMOUNT = Decimal("999999999.99")

SUPPORTED_CURRENCIES = ("USD", "EUR", "ILS", "GBP", "CAD", "AUD", "CHF")
Currency = Literal["USD", "EUR", "ILS", "GBP", "CAD", "AUD", "CHF"]

# Amounts are Decimal everywhere in Python and serialized as JSON numbers (D-09).
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]

# Inputs: at most 2 decimal places, capped at MAX_AMOUNT (D-08). NaN/Infinity are rejected
# by Pydantic's Decimal validation by default.
PositiveAmount = Annotated[Decimal, Field(gt=0, le=MAX_AMOUNT, max_digits=11, decimal_places=2)]
NonNegativeAmount = Annotated[Decimal, Field(ge=0, le=MAX_AMOUNT, max_digits=11, decimal_places=2)]


def trimmed(*, min_length: int = 0, max_length: int) -> Any:
    """A string that is stripped of surrounding whitespace before length checks.

    Applied per field rather than globally: a global `str_strip_whitespace`
    would also strip passwords and silently change them.
    """
    return Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)
    ]


class InputModel(BaseModel):
    """Base for request bodies: unknown fields are rejected (D-13)."""

    model_config = ConfigDict(extra="forbid")


class OutputModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def reject_null(value):
    """For PATCH bodies, used as a field validator on non-nullable columns.

    Field validators don't run for omitted fields (they keep the default None,
    meaning "unchanged"), so this only fires on an explicit `null`, which
    would otherwise reach the database as a NOT NULL violation.
    """
    if value is None:
        raise ValueError("may not be null")
    return value
