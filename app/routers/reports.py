from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app import dates
from app.deps import CurrentUser, DbSession
from app.errors import InvalidInputError
from app.schemas.reports import BudgetStatus, MonthlySummary, SpendingTrend
from app.services import reports as report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@dataclass(frozen=True)
class ReportMonth:
    year: int
    month: int


def report_month(
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
) -> ReportMonth:
    """`year` and `month` together, or neither for the current UTC month."""
    if year is None and month is None:
        today = dates.utc_today()
        return ReportMonth(today.year, today.month)
    if year is None or month is None:
        missing = "year" if year is None else "month"
        raise InvalidInputError(missing, "year and month must be given together")
    return ReportMonth(year, month)


Month = Annotated[ReportMonth, Depends(report_month)]


@router.get("/monthly-summary", response_model=MonthlySummary)
def monthly_summary(user: CurrentUser, db: DbSession, period: Month):
    """Total spending for a month, broken down by category."""
    return report_service.monthly_summary(db, user, period.year, period.month)


@router.get("/trend", response_model=SpendingTrend)
def spending_trend(
    user: CurrentUser,
    db: DbSession,
    months: Annotated[int, Query(ge=1, le=24)] = 6,
):
    """Monthly totals for the last N months (ending with the current month)."""
    return report_service.spending_trend(db, user, months)


@router.get("/budget-status", response_model=BudgetStatus)
def budget_status(user: CurrentUser, db: DbSession, period: Month):
    """Spent vs budget for every category that has a budget in the month."""
    return report_service.budget_status(db, user, period.year, period.month)
