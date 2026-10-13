"""Budget alert on create and update (BAL-01..06)."""

from datetime import date


def warning_of(response):
    assert response.status_code in (200, 201), response.text
    return response.json()["budget_warning"]


# --- on create ---------------------------------------------------------------

def test_no_warning_while_under_budget(api, user, food):
    api.set_budget(user, food, 500)
    assert warning_of(api.create_expense(user, food, 499.99)) is None


def test_no_warning_when_spending_exactly_equals_budget(api, user, food):
    # BAL-03: "exceeds" means strictly greater.
    api.set_budget(user, food, 500)
    api.create_expense(user, food, 300)
    assert warning_of(api.create_expense(user, food, 200)) is None


def test_warning_when_budget_is_exceeded(api, user, food):
    # BAL-01, BAL-02: the example from the assignment.
    api.set_budget(user, food, 500)
    api.create_expense(user, food, 400)
    warning = warning_of(api.create_expense(user, food, 123.50))
    assert warning == {"category": "Food", "budget": 500.0, "spent": 523.5, "exceeded_by": 23.5}


def test_warning_repeats_on_every_expense_while_over_budget(api, user, food):
    # BAL-04
    api.set_budget(user, food, 100)
    api.create_expense(user, food, 150)
    warning = warning_of(api.create_expense(user, food, 0.01))
    assert warning["spent"] == 150.01
    assert warning["exceeded_by"] == 50.01


def test_decimal_math_is_exact(api, user, food):
    # D-09: 0.1 + 0.2 must be 0.3, not 0.30000000000000004.
    api.set_budget(user, food, 0.2)
    api.create_expense(user, food, 0.1)
    warning = warning_of(api.create_expense(user, food, 0.2))
    assert warning["spent"] == 0.3
    assert warning["exceeded_by"] == 0.1


def test_no_warning_without_budget_or_with_zero_budget(api, user, food):
    # BAL-03, D-04
    assert warning_of(api.create_expense(user, food, 1000)) is None
    api.set_budget(user, food, 0)
    assert warning_of(api.create_expense(user, food, 1000)) is None


def test_backdated_expense_is_checked_against_its_own_month(api, user, food):
    # D-03: budget applies to the month of the expense date, not the current month.
    api.set_budget(user, food, 50, year=2026, month=3)
    warning = warning_of(api.create_expense(user, food, 60, day=date(2026, 3, 31)))
    assert warning["exceeded_by"] == 10
    # The current month has no budget, so a large expense today doesn't warn.
    assert warning_of(api.create_expense(user, food, 1000)) is None


def test_only_same_user_category_and_month_count(api, user, food):
    # BAL-01
    transport = api.category_id(user, "Transport")
    api.set_budget(user, food, 100)
    api.create_expense(user, transport, 500)                     # other category
    api.create_expense(user, food, 500, day=date(2026, 5, 31))   # previous month
    other = api.new_user()
    api.create_expense(other, api.category_id(other, "Food"), 500)  # other user

    assert warning_of(api.create_expense(user, food, 100)) is None  # exactly 100 spent


# --- on update ---------------------------------------------------------------

def test_update_raising_amount_over_budget_warns(api, client, user, food):
    # BAL-05, EXP-10: same response shape as POST.
    api.set_budget(user, food, 100)
    expense_id = api.create_expense(user, food, 80).json()["expense"]["id"]

    response = client.patch(f"/expenses/{expense_id}", json={"amount": 130.25}, headers=user)
    assert set(response.json()) == {"expense", "budget_warning"}
    assert warning_of(response) == {"category": "Food", "budget": 100.0, "spent": 130.25, "exceeded_by": 30.25}


def test_update_lowering_amount_under_budget_clears_warning(api, client, user, food):
    # BAL-03, BAL-05
    api.set_budget(user, food, 100)
    expense_id = api.create_expense(user, food, 150).json()["expense"]["id"]
    response = client.patch(f"/expenses/{expense_id}", json={"amount": 90}, headers=user)
    assert warning_of(response) is None


def test_moving_expense_to_another_category_checks_the_new_category(api, client, user, food):
    # BAL-05, BAL-06
    transport = api.category_id(user, "Transport")
    api.set_budget(user, food, 100)
    api.set_budget(user, transport, 50)
    api.create_expense(user, transport, 40)
    expense_id = api.create_expense(user, food, 120).json()["expense"]["id"]  # Food is over budget

    response = client.patch(f"/expenses/{expense_id}", json={"category_id": transport}, headers=user)
    warning = warning_of(response)
    assert warning == {"category": "Transport", "budget": 50.0, "spent": 160.0, "exceeded_by": 110.0}

    # The old category no longer counts the moved expense; the new one does.
    status = {item["category_name"]: item for item in client.get("/reports/budget-status", headers=user).json()["items"]}
    assert status["Food"]["spent"] == 0
    assert status["Food"]["exceeded"] is False
    assert status["Transport"]["spent"] == 160


def test_moving_expense_to_another_month_checks_that_month(api, client, user, food):
    # BAL-05, BAL-06
    api.set_budget(user, food, 100, year=2026, month=5)
    api.create_expense(user, food, 70, day=date(2026, 5, 10))
    expense_id = api.create_expense(user, food, 50).json()["expense"]["id"]  # June, no budget

    response = client.patch(f"/expenses/{expense_id}", json={"date": "2026-05-20"}, headers=user)
    assert warning_of(response) == {"category": "Food", "budget": 100.0, "spent": 120.0, "exceeded_by": 20.0}

    june = client.get("/reports/monthly-summary", params={"year": 2026, "month": 6}, headers=user).json()
    may = client.get("/reports/monthly-summary", params={"year": 2026, "month": 5}, headers=user).json()
    assert june["total"] == 0
    assert may["total"] == 120


def test_update_of_other_fields_still_reports_existing_overspend(api, client, user, food):
    # BAL-04: consistent with POST — the month is over budget after this change.
    api.set_budget(user, food, 100)
    expense_id = api.create_expense(user, food, 150).json()["expense"]["id"]
    response = client.patch(f"/expenses/{expense_id}", json={"description": "Groceries"}, headers=user)
    assert warning_of(response)["exceeded_by"] == 50
