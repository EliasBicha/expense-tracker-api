import uuid

import pytest


def test_set_budget_creates_then_updates(api, client, user, food):
    # BUD-01
    created = api.set_budget(user, food, 500)
    assert created.status_code == 201
    assert created.json()["category_name"] == "Food"

    updated = api.set_budget(user, food, 650.75)
    assert updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"]
    assert updated.json()["amount"] == 650.75

    budgets = client.get("/budgets", headers=user).json()
    assert len(budgets) == 1


def test_past_and_future_months_are_allowed(api, user, food):
    # BUD-04: retroactive tracking.
    assert api.set_budget(user, food, 100, year=2020, month=1).status_code == 201
    assert api.set_budget(user, food, 100, year=2027, month=12).status_code == 201


@pytest.mark.parametrize(
    "amount, year, month, expected",
    [
        (0, 2026, 6, 201),             # BUD-03: zero allowed
        (-1, 2026, 6, 422),            # negative rejected
        (1_000_000_000, 2026, 6, 422),  # above the cap
        (10.555, 2026, 6, 422),        # more than 2 decimals
        (100, 1999, 6, 422),           # BUD-04 year range
        (100, 2026, 13, 422),          # month range
        (100, 2026, 0, 422),
    ],
)
def test_budget_validation(api, user, food, amount, year, month, expected):
    assert api.set_budget(user, food, amount, year=year, month=month).status_code == expected


def test_list_budgets_with_filters_and_order(api, client, user, food):
    # BUD-05
    transport = api.category_id(user, "Transport")
    api.set_budget(user, transport, 1, year=2026, month=6)
    api.set_budget(user, food, 2, year=2026, month=6)
    api.set_budget(user, food, 3, year=2026, month=5)
    api.set_budget(user, food, 4, year=2025, month=12)

    budgets = client.get("/budgets", headers=user).json()
    assert [(b["year"], b["month"], b["category_name"]) for b in budgets] == [
        (2026, 6, "Food"),
        (2026, 6, "Transport"),
        (2026, 5, "Food"),
        (2025, 12, "Food"),
    ]
    june = client.get("/budgets", params={"year": 2026, "month": 6}, headers=user).json()
    assert [b["amount"] for b in june] == [2, 1]


def test_delete_budget_and_ownership(api, client, user, food):
    # BUD-06, SEC-02
    budget_id = api.set_budget(user, food, 100).json()["id"]
    intruder = api.new_user()

    assert client.delete(f"/budgets/{budget_id}", headers=intruder).status_code == 404
    assert client.get("/budgets", headers=intruder).json() == []
    assert client.delete(f"/budgets/{budget_id}", headers=user).status_code == 204
    assert client.delete(f"/budgets/{budget_id}", headers=user).status_code == 404
    assert client.delete(f"/budgets/{uuid.uuid4()}", headers=user).status_code == 404


def test_budgets_are_per_user(api, client, user, food):
    # Two users can budget the same system category independently.
    other = api.new_user()
    assert api.set_budget(user, food, 100).status_code == 201
    assert api.set_budget(other, food, 200).status_code == 201
    assert client.get("/budgets", headers=user).json()[0]["amount"] == 100
