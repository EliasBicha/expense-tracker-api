from fastapi import APIRouter, status

from app.deps import CurrentUser, DbSession
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut, UserUpdate
from app.security import create_access_token
from app.services import users as user_service

router = APIRouter(tags=["auth & users"])


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: DbSession):
    """Create an account. Log in afterwards to get a token."""
    return user_service.register(db, data)


@router.post("/auth/login", response_model=TokenResponse)
def login(data: LoginRequest, db: DbSession):
    """Exchange email and password for a bearer token."""
    user = user_service.authenticate(db, data.email, data.password)
    token, expires_in = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/users/me", response_model=UserOut)
def get_me(user: CurrentUser):
    return user


@router.patch("/users/me", response_model=UserOut)
def update_me(data: UserUpdate, user: CurrentUser, db: DbSession):
    """Update display name and/or default currency."""
    return user_service.update_profile(db, user, data)
