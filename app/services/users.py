from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AuthError, ConflictError
from app.models import Budget, Expense, User
from app.schemas.auth import RegisterRequest, UserUpdate
from app.security import hash_password, verify_dummy_password, verify_password

INVALID_CREDENTIALS = "Invalid email or password"


def register(db: Session, data: RegisterRequest) -> User:
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
        default_currency=data.default_currency,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # The unique constraint on email is the source of truth: a check-then-insert
        # would still race with a concurrent registration.
        db.rollback()
        raise ConflictError("An account with this email already exists", code="email_taken")
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        verify_dummy_password(password)  # same cost as a real check (AUTH-05)
        raise AuthError(INVALID_CREDENTIALS, code="invalid_credentials")
    if not verify_password(password, user.password_hash):
        raise AuthError(INVALID_CREDENTIALS, code="invalid_credentials")
    return user


def update_profile(db: Session, user: User, data: UserUpdate) -> User:
    changes = data.model_dump(exclude_unset=True)
    new_currency = changes.get("default_currency")
    if new_currency is not None and new_currency != user.default_currency:
        has_amounts = db.scalar(
            select(
                exists().where(Expense.user_id == user.id)
                | exists().where(Budget.user_id == user.id)
            )
        )
        if has_amounts:
            # Expenses and budgets are stored in the old currency and there is no conversion,
            # so allowing this would mix currencies in reports and budget checks (D-05, USR-03).
            raise ConflictError(
                "Default currency can't be changed after expenses or budgets have been recorded",
                code="currency_change_blocked",
            )
    for field, value in changes.items():
        setattr(user, field, value)
    db.commit()
    return user
