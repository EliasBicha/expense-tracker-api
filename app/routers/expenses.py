import csv
import io
import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbSession
from app.errors import InvalidInputError
from app.models import User
from app.schemas.common import MAX_AMOUNT
from app.schemas.expenses import (
    ExpenseCreate,
    ExpenseList,
    ExpenseOut,
    ExpenseUpdate,
    ExpenseWithWarning,
)
from app.services import expenses as expense_service
from app.services.expenses import ExpenseFilters

router = APIRouter(prefix="/expenses", tags=["expenses"])

# PostgreSQL's OFFSET is a BIGINT; anything larger is rejected by the database.
MAX_OFFSET = 2**63 - 1


def expense_filters(
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: uuid.UUID | None = None,
    # Same range and precision as stored amounts. Values outside it are meaningless as filters,
    # and extreme ones (very large, or with thousands of decimals) overflow in PostgreSQL.
    min_amount: Annotated[Decimal | None, Query(ge=0, le=MAX_AMOUNT, decimal_places=2)] = None,
    max_amount: Annotated[Decimal | None, Query(ge=0, le=MAX_AMOUNT, decimal_places=2)] = None,
) -> ExpenseFilters:
    """Query-string filters shared by the list and export endpoints (EXP-08)."""
    if date_from and date_to and date_from > date_to:
        raise InvalidInputError("date_from", "date_from must not be after date_to")
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise InvalidInputError("min_amount", "min_amount must not be greater than max_amount")
    return ExpenseFilters(date_from, date_to, category_id, min_amount, max_amount)


Filters = Annotated[ExpenseFilters, Depends(expense_filters)]


@router.get("", response_model=ExpenseList)
def list_expenses(
    user: CurrentUser,
    db: DbSession,
    filters: Filters,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
):
    """Your expenses, newest first, with optional filters and pagination."""
    items, total = expense_service.list_expenses(db, user, filters, limit, offset)
    return ExpenseList(items=items, total=total, limit=limit, offset=offset)


# Declared before "/{expense_id}" so "export" isn't parsed as an expense id.
@router.get("/export", response_class=StreamingResponse)
def export_expenses(user: CurrentUser, db: DbSession, filters: Filters):
    """Download the filtered expenses as CSV (no pagination)."""
    return StreamingResponse(
        _csv_lines(db, user, filters),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="expenses.csv"'},
    )


CSV_HEADER = ("id", "date", "amount", "currency", "category", "description", "receipt_url")
# Spreadsheet apps treat cells starting with these as formulas (CSV injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def _csv_lines(db: Session, user: User, filters: ExpenseFilters) -> Iterator[str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    def flush() -> str:
        line = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return line

    writer.writerow(CSV_HEADER)
    yield flush()
    for row in expense_service.iter_export_rows(db, user, filters):
        writer.writerow([_csv_safe(value) for value in row])
        yield flush()


@router.post("", response_model=ExpenseWithWarning, status_code=status.HTTP_201_CREATED)
def create_expense(data: ExpenseCreate, user: CurrentUser, db: DbSession):
    """Record an expense. `budget_warning` is set if this leaves the month over budget."""
    expense, warning = expense_service.create_expense(db, user, data)
    return ExpenseWithWarning(expense=expense, budget_warning=warning)


@router.get("/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return expense_service.get_expense(db, user, expense_id)


@router.patch("/{expense_id}", response_model=ExpenseWithWarning)
def update_expense(expense_id: uuid.UUID, data: ExpenseUpdate, user: CurrentUser, db: DbSession):
    """Partial update. Same response shape and budget check as creation."""
    expense, warning = expense_service.update_expense(db, user, expense_id, data)
    return ExpenseWithWarning(expense=expense, budget_warning=warning)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(expense_id: uuid.UUID, user: CurrentUser, db: DbSession):
    expense_service.delete_expense(db, user, expense_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
