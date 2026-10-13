"""Test fixtures.

Tests run against a real PostgreSQL database (D-02), selected by DATABASE_URL.
The schema is built once per session by running the Alembic migrations, so the
migrations themselves are exercised. Each test runs inside a transaction that is
rolled back afterwards, so tests are isolated and leave no data behind.

Because rebuilding the schema drops every table, the suite refuses to run unless
the database name ends in "_test".
"""

from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import dates
from app.config import get_settings
from app.db import engine, get_db
from app.main import app

ROOT = Path(__file__).resolve().parent.parent

# Every test runs "on" this date so month boundaries and the +7 day rule are deterministic.
TODAY = date(2026, 6, 15)


class UnsafeDatabaseError(Exception):
    pass


def reset_test_database(database_url: str) -> None:
    """Rebuild the schema with the migrations, but only on a database named *_test.

    `downgrade base` drops every table, so the name is checked first, before any
    migration runs or any connection is made. A DATABASE_URL accidentally pointing
    at development or production data is refused instead of wiped.
    """
    database = make_url(database_url).database or ""
    if not database.endswith("_test"):
        # Only the database name is shown: the full URL contains the password.
        raise UnsafeDatabaseError(
            f"Refusing to run tests against database {database!r}: the test setup resets the "
            "schema, so it only runs against a database whose name ends in '_test'."
        )
    config = Config(str(ROOT / "alembic.ini"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    try:
        reset_test_database(get_settings().database_url)
    except UnsafeDatabaseError as exc:
        pytest.exit(str(exc), returncode=1)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(dates, "utc_today", lambda: TODAY)
    return TODAY


@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    # "create_savepoint": the services' commit()/rollback() only act on a SAVEPOINT,
    # so the outer transaction can still be rolled back at the end of the test.
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class Api:
    """Small helper around TestClient for creating users and common records."""

    _counter = 0

    def __init__(self, client: TestClient):
        self.client = client

    def register(self, email: str | None = None, password: str = "correct-horse-1", **extra):
        if email is None:
            Api._counter += 1
            email = f"user{Api._counter}@example.com"
        body = {"email": email, "password": password, "display_name": "Test User", **extra}
        return self.client.post("/auth/register", json=body)

    def login(self, email: str, password: str = "correct-horse-1"):
        return self.client.post("/auth/login", json={"email": email, "password": password})

    def new_user(self, **extra) -> dict:
        """Register + log in; returns Authorization headers."""
        response = self.register(**extra)
        assert response.status_code == 201, response.text
        token = self.login(response.json()["email"]).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def category_id(self, headers: dict, name: str) -> str:
        categories = self.client.get("/categories", headers=headers).json()
        return next(c["id"] for c in categories if c["name"] == name)

    def create_category(self, headers: dict, name: str = "Coffee", **extra):
        body = {"name": name, "icon": "coffee", "color": "#6F4E37", **extra}
        return self.client.post("/categories", json=body, headers=headers)

    def create_expense(self, headers: dict, category_id: str, amount, day: date | str = TODAY, **extra):
        body = {"amount": amount, "category_id": category_id, "date": str(day), **extra}
        return self.client.post("/expenses", json=body, headers=headers)

    def set_budget(self, headers: dict, category_id: str, amount, year: int = TODAY.year, month: int = TODAY.month):
        body = {"category_id": category_id, "year": year, "month": month, "amount": amount}
        return self.client.put("/budgets", json=body, headers=headers)


@pytest.fixture
def api(client) -> Api:
    return Api(client)


@pytest.fixture
def user(api) -> dict:
    """Authorization headers for a fresh user."""
    return api.new_user()


@pytest.fixture
def food(api, user) -> str:
    """Id of the system "Food" category."""
    return api.category_id(user, "Food")
