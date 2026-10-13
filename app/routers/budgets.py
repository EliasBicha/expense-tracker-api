import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.deps import CurrentUser, DbSession
from app.models import Budget
from app.schemas.budgets import BudgetOut, BudgetUpsert
from app.services import budgets as budget_service

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _to_out(budget: Budget, category_name: str) -> BudgetOut:
    return BudgetOut(
        id=budget.id,
        category_id=budget.category_id,
        category_name=category_name,
        year=budget.year,
        month=budget.month,
        amount=budget.amount,
    )


@router.put(
    "",
    response_model=BudgetOut,
    status_code=status.HTTP_200_OK,
    responses={201: {"model": BudgetOut, "description": "Budget created"}},
)
def set_budget(data: BudgetUpsert, user: CurrentUser, db: DbSession, response: Response):
    """Create (201) or update (200) the budget for a category and month.

    Past months are allowed for retroactive tracking; an amount of 0 tracks without a limit.
    """
    budget, category, created = budget_service.upsert_budget(db, user, data)
    if created:
        response.status_code = status.HTTP_201_CREATED
    return _to_out(budget, category.name)


@router.get("", response_model=list[BudgetOut])
def list_budgets(
    user: CurrentUser,
    db: DbSession,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
):
    rows = budget_service.list_budgets(db, user, year, month)
    return [_to_out(budget, category_name) for budget, category_name in rows]


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(budget_id: uuid.UUID, user: CurrentUser, db: DbSession):
    budget_service.delete_budget(db, user, budget_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
