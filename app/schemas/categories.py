import uuid
from typing import Annotated

from pydantic import StringConstraints, field_validator

from app.schemas.common import InputModel, OutputModel, reject_null, trimmed

CategoryName = trimmed(min_length=1, max_length=50)
Icon = Annotated[str, StringConstraints(min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")]
Color = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]


class CategoryCreate(InputModel):
    name: CategoryName
    icon: Icon
    color: Color


class CategoryUpdate(InputModel):
    name: CategoryName | None = None
    icon: Icon | None = None
    color: Color | None = None

    _no_nulls = field_validator("name", "icon", "color")(reject_null)


class CategoryOut(OutputModel):
    id: uuid.UUID
    name: str
    icon: str
    color: str
    is_system: bool
