from datetime import date


def test_monthly_summary_totals_by_category(api, client, user, food):
    # RPT-01
    transport = api.category_id(user, "Transport")
    api.create_expense(user, food, 10.10, day=date(2026, 6, 1))
    api.create_expense(user, food, 20.20, day=date(2026, 6, 22))  # latest allowed date (+7 days)
    api.create_expense(user, transport, 45, day=date(2026, 6, 15))
    api.create_expense(user, food, 999, day=date(2026, 5, 31))  # previous month: excluded

    summary = client.get("/reports/monthly-summary", params={"year": 2026, "month": 6}, headers=user).json()
    assert summary["currency"] == "USD"
    assert summary["total"] == 75.3
    assert summary["by_category"] == [
        {"category_id": transport, "category_name": "Transport", "total": 45.0},
        {"category_id": food, "category_name": "Food", "total": 30.3},
    ]


def test_monthly_summary_defaults_to_current_month_and_handles_empty(client, user):
    # RPT-01
    summary = client.get("/reports/monthly-summary", headers=user).json()
    assert (summary["year"], summary["month"]) == (2026, 6)
    assert summary["total"] == 0
    assert summary["by_category"] == []


def test_report_month_requires_year_and_month_together(client, user):
    # RPT-05
    response = client.get("/reports/monthly-summary", params={"year": 2026}, headers=user)
    assert response.status_code == 422


def test_spending_trend(api, client, user, food):
    # RPT-02: oldest to newest, ending with the current month, zero-filled.
    api.create_expense(user, food, 100, day=date(2026, 3, 5))
    api.create_expense(user, food, 50, day=date(2026, 3, 25))
    api.create_expense(user, food, 300, day=date(2026, 5, 1))
    api.create_expense(user, food, 75, day=date(2026, 6, 15))
    api.create_expense(user, food, 999, day=date(2026, 1, 31))  # before the window

    trend = client.get("/reports/trend", params={"months": 4}, headers=user).json()
    assert trend["months"] == [
        {"year": 2026, "month": 3, "total": 150.0, "change_amount": None, "change_percent": None},
        {"year": 2026, "month": 4, "total": 0.0, "change_amount": -150.0, "change_percent": -100.0},
        # previous month was 0: percentage change is undefined
        {"year": 2026, "month": 5, "total": 300.0, "change_amount": 300.0, "change_percent": None},
        {"year": 2026, "month": 6, "total": 75.0, "change_amount": -225.0, "change_percent": -75.0},
    ]


def test_spending_trend_crosses_year_boundary_and_validates_n(client, user):
    # RPT-02
    trend = client.get("/reports/trend", params={"months": 8}, headers=user).json()
    assert [(m["year"], m["month"]) for m in trend["months"]][:2] == [(2025, 11), (2025, 12)]
    assert len(trend["months"]) == 8
    assert len(client.get("/reports/trend", headers=user).json()["months"]) == 6  # default
    assert client.get("/reports/trend", params={"months": 0}, headers=user).status_code == 422
    assert client.get("/reports/trend", params={"months": 25}, headers=user).status_code == 422


def test_budget_status(api, client, user, food):
    # RPT-03
    transport = api.category_id(user, "Transport")
    health = api.category_id(user, "Health")
    shopping = api.category_id(user, "Shopping")
    api.set_budget(user, food, 500)
    api.set_budget(user, transport, 100)
    api.set_budget(user, health, 0)  # tracked, no limit
    api.create_expense(user, food, 523.50)
    api.create_expense(user, transport, 33.33)
    api.create_expense(user, health, 80)
    api.create_expense(user, shopping, 10)  # no budget: not listed

    status = client.get("/reports/budget-status", params={"year": 2026, "month": 6}, headers=user).json()
    assert status["items"] == [
        {
            "category_id": food, "category_name": "Food", "budget": 500.0, "spent": 523.5,
            "remaining": -23.5, "percent_used": 104.7, "exceeded": True, "has_limit": True,
        },
        {
            "category_id": health, "category_name": "Health", "budget": 0.0, "spent": 80.0,
            "remaining": -80.0, "percent_used": None, "exceeded": False, "has_limit": False,
        },
        {
            "category_id": transport, "category_name": "Transport", "budget": 100.0, "spent": 33.33,
            "remaining": 66.67, "percent_used": 33.33, "exceeded": False, "has_limit": True,
        },
    ]


def test_budget_status_with_no_spending(api, client, user, food):
    # RPT-03
    api.set_budget(user, food, 200)
    item = client.get("/reports/budget-status", headers=user).json()["items"][0]
    assert (item["spent"], item["remaining"], item["percent_used"], item["exceeded"]) == (0, 200, 0, False)


def test_reports_only_include_own_data(api, client, user, food):
    # RPT-04
    other = api.new_user()
    other_food = api.category_id(other, "Food")
    api.create_expense(other, other_food, 1000)
    api.set_budget(other, other_food, 10)
    api.create_expense(user, food, 5)

    assert client.get("/reports/monthly-summary", headers=user).json()["total"] == 5
    assert client.get("/reports/trend", headers=user).json()["months"][-1]["total"] == 5
    assert client.get("/reports/budget-status", headers=user).json()["items"] == []
