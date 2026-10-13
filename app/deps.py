from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import AuthError
from app.models import User
from app.security import decode_access_token

# auto_error=False: we raise our own AuthError so every auth failure is a 401
# in the standard error envelope.
_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise AuthError("Not authenticated")
    user_id = decode_access_token(credentials.credentials)
    user = db.get(User, user_id)
    if user is None:
        raise AuthError("Invalid or expired token")
    request.state.user_id = str(user.id)  # picked up by the request log line
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
