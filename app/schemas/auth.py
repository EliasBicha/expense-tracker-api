import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, EmailStr, Field, field_validator

from app.schemas.common import Currency, InputModel, OutputModel, reject_null, trimmed

# Lowercased so lookups and the unique constraint are case-insensitive (AUTH-02).
Email = Annotated[EmailStr, AfterValidator(str.lower)]
Password = Annotated[str, Field(min_length=8, max_length=128)]
DisplayName = trimmed(min_length=1, max_length=100)


class RegisterRequest(InputModel):
    email: Email
    password: Password
    display_name: DisplayName
    default_currency: Currency = "USD"


class LoginRequest(InputModel):
    # Not EmailStr: a malformed email should be an ordinary failed login (401),
    # and the length cap keeps hashing cost bounded.
    email: Annotated[str, Field(min_length=1, max_length=320)]
    password: Annotated[str, Field(min_length=1, max_length=128)]


class TokenResponse(OutputModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserOut(OutputModel):
    id: uuid.UUID
    email: str
    display_name: str
    default_currency: str
    created_at: datetime
    updated_at: datetime


class UserUpdate(InputModel):
    display_name: DisplayName | None = None
    default_currency: Currency | None = None

    _no_nulls = field_validator("display_name", "default_currency")(reject_null)
