from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.deps import DbSession

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: DbSession):
    """Liveness + database connectivity (OPS-01)."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
