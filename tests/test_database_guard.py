"""The test suite must never reset a database that isn't a test database.

Migrations are replaced with recorders and the URLs point at an unreachable host,
so these tests can't touch any real database.
"""

import pytest
from alembic import command

from tests.conftest import UnsafeDatabaseError, reset_test_database

UNREACHABLE = "postgresql+psycopg://user:s3cret-pw@unreachable.invalid:1"


@pytest.fixture
def migration_calls(monkeypatch) -> list[str]:
    calls = []
    monkeypatch.setattr(command, "downgrade", lambda config, revision: calls.append("downgrade"))
    monkeypatch.setattr(command, "upgrade", lambda config, revision: calls.append("upgrade"))
    return calls


@pytest.mark.parametrize("database", ["expenses", "expenses_testing", "test_expenses", ""])
def test_non_test_database_is_refused_before_any_migration(migration_calls, database):
    with pytest.raises(UnsafeDatabaseError) as refused:
        reset_test_database(f"{UNREACHABLE}/{database}")
    assert migration_calls == []  # nothing ran, and nothing tried to connect
    assert "s3cret-pw" not in str(refused.value)  # the password is never shown


def test_test_database_is_migrated(migration_calls):
    reset_test_database(f"{UNREACHABLE}/expenses_test")
    assert migration_calls == ["downgrade", "upgrade"]
