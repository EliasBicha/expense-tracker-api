import uuid

from fastapi import APIRouter, Response, status

from app.deps import CurrentUser, DbSession
from app.schemas.categories import CategoryCreate, CategoryOut, CategoryUpdate
from app.services import categories as category_service

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(user: CurrentUser, db: DbSession):
    """System default categories followed by your own."""
    return category_service.list_categories(db, user)


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryCreate, user: CurrentUser, db: DbSession):
    return category_service.create_category(db, user, data)


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: uuid.UUID, data: CategoryUpdate, user: CurrentUser, db: DbSession
):
    return category_service.update_category(db, user, category_id, data)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: uuid.UUID, user: CurrentUser, db: DbSession):
    """Fails with 409 and the expense count if any expense still uses the category."""
    category_service.delete_category(db, user, category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
