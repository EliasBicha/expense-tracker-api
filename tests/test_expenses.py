import uuid
from datetime import date, timedelta

import pytest

from tests.conftest import TODAY


def test_expense_crud_lifecycle(api, client, user, food):
    # EXP-01, EXP-06, EXP-09, EXP-10, EXP-11
    created = api.create_expense(
        user, food, 12.5, description="Lunch", receipt_url="https://example.com/r/1.png"
    )
    assert created.status_code == 201
    body = created.json()
    assert body["budget_warning"] is None
    expense = body["expense"]
    assert expense["amount"] == 12.5
    assert expense["currency"] == "USD"  # from the user's default currency
    assert expense["date"] == str(TODAY)
    assert expense["description"] == "Lunch"
    expense_id = expense["id"]

    assert client.get(f"/expenses/{expense_id}", headers=user).json() == expense

    updated = client.patch(
        f"/expenses/{expense_id}", json={"amount": 15, "description": None}, headers=user
    )
    assert updated.status_code == 200
    assert updated.json()["expense"]["amount"] == 15
    assert updated.json()["expense"]["description"] is None  # explicit null clears it
    assert updated.json()["expense"]["receipt_url"] == "https://example.com/r/1.png"  # untouched

    assert client.delete(f"/expenses/{expense_id}", headers=user).status_code == 204
    assert client.get(f"/expenses/{expense_id}", headers=user).status_code == 404


@pytest.mark.parametrize("amount", [-1, 0, 1_000_000_000, 999999999.991, 10.123, "NaN", "Infinity", "abc"])
def test_invalid_amounts_are_rejected(api, user, food, amount):
    # EXP-03, D-08
    response = api.create_expense(user, food, amount)
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "amount"


@pytest.mark.parametrize("amount", [0.01, 999999999.99, "19.90"])
def test_boundary_amounts_are_accepted(api, user, food, amount):
    # EXP-03, D-08
    assert api.create_expense(user, food, amount).status_code == 201


def test_future_date_limit(api, client, user, food):
    # EXP-04: up to 7 days ahead (inclusive), also on update.
    assert api.create_expense(user, food, 5, day=TODAY + timedelta(days=7)).status_code == 201
    too_far = api.create_expense(user, food, 5, day=TODAY + timedelta(days=8))
    assert too_far.status_code == 422
    assert too_far.json()["error"]["details"][0]["field"] == "date"
    assert api.create_expense(user, food, 5, day=date(1999, 12, 31)).status_code == 422

    expense_id = api.create_expense(user, food, 5).json()["expense"]["id"]
    response = client.patch(
        f"/expenses/{expense_id}", json={"date": str(TODAY + timedelta(days=8))}, headers=user
    )
    assert response.status_code == 422


@pytest.mark.parametrize("field, value", [("currency", "EUR"), ("user_id", str(uuid.uuid4())), ("id", str(uuid.uuid4()))])
def test_server_controlled_fields_are_rejected(api, user, food, field, value):
    # EXP-06, D-13
    response = api.create_expense(user, food, 5, **{field: value})
    assert response.status_code == 422


@pytest.mark.parametrize("url", ["ftp://example.com/r.png", "javascript:alert(1)", "not a url"])
def test_receipt_url_must_be_http(api, user, food, url):
    # EXP-05
    assert api.create_expense(user, food, 5, receipt_url=url).status_code == 422


def test_receipt_url_is_stored_in_normalized_form(api, user, food):
    # EXP-05: the URL validator's standard form is what gets stored.
    expense = api.create_expense(user, food, 5, receipt_url="HTTPS://Example.COM").json()["expense"]
    assert expense["receipt_url"] == "https://example.com/"
    expense = api.create_expense(user, food, 5, receipt_url="https://example.com/r/1.png").json()["expense"]
    assert expense["receipt_url"] == "https://example.com/r/1.png"  # already standard: unchanged


def test_receipt_url_too_long_once_normalized_is_rejected(api, client, user, food):
    # EXP-05: each space becomes %20, so a 2048-character input can exceed the 2048 column
    # limit after normalization. It must be a 422, not a database error.
    base = "https://example.com/"
    url = base + "a b" * ((2048 - len(base)) // 3)
    url += "a" * (2048 - len(url))
    assert len(url) == 2048

    created = api.create_expense(user, food, 5, receipt_url=url)
    assert created.status_code == 422
    assert created.json()["error"]["details"][0]["field"] == "receipt_url"

    expense_id = api.create_expense(user, food, 5).json()["expense"]["id"]
    updated = client.patch(f"/expenses/{expense_id}", json={"receipt_url": url}, headers=user)
    assert updated.status_code == 422


@pytest.mark.parametrize(
    "url, expected_status",
    [
        ("https://example.com/" + "a" * 2028, 201),  # 2048 characters, unchanged by normalization
        ("https://example.com?" + "q" * 2027, 201),  # 2047 + the "/" normalization adds = 2048
        ("https://example.com?" + "q" * 2028, 422),  # 2048 + the added "/" = 2049
    ],
    ids=["2048-unchanged", "2047-plus-slash-is-2048", "2048-plus-slash-is-2049"],
)
def test_receipt_url_length_limit_applies_to_the_stored_form(api, user, food, url, expected_status):
    # EXP-05: boundaries around the 2048-character limit, measured after normalization.
    response = api.create_expense(user, food, 5, receipt_url=url)
    assert response.status_code == expected_status
    if expected_status == 201:
        assert len(response.json()["expense"]["receipt_url"]) == 2048


def test_empty_description_is_stored_as_null(api, client, user, food):
    # EXP-05: "" and whitespace-only mean "no description", same as omitting it.
    for description in ("", "   "):
        expense = api.create_expense(user, food, 5, description=description).json()["expense"]
        assert expense["description"] is None

    expense_id = api.create_expense(user, food, 5, description="Lunch").json()["expense"]["id"]
    response = client.patch(f"/expenses/{expense_id}", json={"description": ""}, headers=user)
    assert response.json()["expense"]["description"] is None


def test_patch_rejects_null_for_required_fields(api, client, user, food):
    # EXP-10
    expense_id = api.create_expense(user, food, 5).json()["expense"]["id"]
    for field in ("amount", "category_id", "date"):
        response = client.patch(f"/expenses/{expense_id}", json={field: None}, headers=user)
        assert response.status_code == 422, field


def test_list_filters(api, client, user, food):
    # EXP-08
    transport = api.category_id(user, "Transport")
    api.create_expense(user, food, 10, day=date(2026, 5, 1))
    api.create_expense(user, food, 20, day=date(2026, 5, 31))
    api.create_expense(user, transport, 30, day=date(2026, 6, 1))
    api.create_expense(user, food, 40, day=date(2026, 6, 10))

    def amounts(**params):
        response = client.get("/expenses", params=params, headers=user)
        assert response.status_code == 200
        return sorted(item["amount"] for item in response.json()["items"])

    assert amounts() == [10, 20, 30, 40]
    assert amounts(date_from="2026-05-31", date_to="2026-06-01") == [20, 30]  # inclusive
    assert amounts(category_id=transport) == [30]
    assert amounts(min_amount=20, max_amount=30) == [20, 30]  # inclusive
    assert amounts(category_id=food, date_from="2026-06-01") == [40]


def test_list_pagination_and_ordering(api, client, user, food):
    # EXP-07
    for day in range(1, 6):
        api.create_expense(user, food, day, day=date(2026, 6, day))

    page = client.get("/expenses", params={"limit": 2, "offset": 1}, headers=user).json()
    assert page["total"] == 5
    assert (page["limit"], page["offset"]) == (2, 1)
    assert [item["date"] for item in page["items"]] == ["2026-06-04", "2026-06-03"]  # newest first

    assert client.get("/expenses", params={"limit": 101}, headers=user).status_code == 422
    assert client.get("/expenses", params={"limit": 0}, headers=user).status_code == 422


def test_inverted_ranges_are_rejected(client, user):
    # EXP-08
    bad_dates = client.get("/expenses", params={"date_from": "2026-06-02", "date_to": "2026-06-01"}, headers=user)
    assert bad_dates.status_code == 422
    assert bad_dates.json()["error"]["details"][0]["field"] == "date_from"
    bad_amounts = client.get("/expenses", params={"min_amount": 50, "max_amount": 10}, headers=user)
    assert bad_amounts.status_code == 422


def test_negative_amount_filters_are_rejected(client, user):
    # EXP-08
    for param in ("min_amount", "max_amount"):
        response = client.get("/expenses", params={param: -1}, headers=user)
        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["field"] == param


@pytest.mark.parametrize(
    "param, value",
    [
        ("offset", 2**63),  # one past PostgreSQL's BIGINT maximum
        ("offset", 10**30),
        ("min_amount", "1000000000"),  # just above the 999,999,999.99 amount cap
        ("min_amount", "1e200000"),
        ("max_amount", "1e200000"),
        ("min_amount", "1e-20000"),  # tiny, but overflows PostgreSQL's numeric type
        ("max_amount", "1e-20000"),
        ("min_amount", "10.555"),  # more than 2 decimal places
    ],
)
def test_out_of_range_list_parameters_are_rejected(client, user, param, value):
    # EXP-07, EXP-08: values the database can't represent are a 422, not a 500.
    response = client.get("/expenses", params={param: value}, headers=user)
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == param


@pytest.mark.parametrize(
    "param, value",
    [("offset", 2**63 - 1), ("min_amount", "999999999.99"), ("max_amount", "999999999.99")],
)
def test_list_parameters_at_their_limits_are_accepted(api, client, user, food, param, value):
    # EXP-07, EXP-08: the largest valid values still work.
    api.create_expense(user, food, 999999999.99)
    response = client.get("/expenses", params={param: value}, headers=user)
    assert response.status_code == 200
    expected_total = 0 if param == "offset" else 1  # a huge offset just returns an empty page
    assert len(response.json()["items"]) == expected_total


def test_amount_filters_with_valid_precision_still_filter(api, client, user, food):
    # EXP-08: values with 0, 1 or 2 decimal places keep working as inclusive bounds.
    api.create_expense(user, food, 10.50)
    api.create_expense(user, food, 10.55)

    def amounts(**params):
        response = client.get("/expenses", params=params, headers=user)
        assert response.status_code == 200
        return sorted(item["amount"] for item in response.json()["items"])

    assert amounts(min_amount="0") == [10.5, 10.55]
    assert amounts(min_amount="10.55") == [10.55]
    assert amounts(max_amount="10.5") == [10.5]
    assert amounts(min_amount="0.01", max_amount="11") == [10.5, 10.55]


def test_users_cannot_see_or_change_each_others_expenses(api, client, user, food):
    # SEC-02, EXP-09, EXP-10, EXP-11
    expense_id = api.create_expense(user, food, 99).json()["expense"]["id"]
    intruder = api.new_user()

    assert client.get(f"/expenses/{expense_id}", headers=intruder).status_code == 404
    assert client.patch(f"/expenses/{expense_id}", json={"amount": 1}, headers=intruder).status_code == 404
    assert client.delete(f"/expenses/{expense_id}", headers=intruder).status_code == 404
    assert client.get("/expenses", headers=intruder).json()["total"] == 0
    # ...and the owner's expense is unchanged.
    assert client.get(f"/expenses/{expense_id}", headers=user).json()["amount"] == 99


def test_cannot_move_expense_into_another_users_category(api, client, user, food):
    # EXP-02, EXP-10
    expense_id = api.create_expense(user, food, 5).json()["expense"]["id"]
    foreign = api.create_category(api.new_user(), "Private").json()["id"]
    response = client.patch(f"/expenses/{expense_id}", json={"category_id": foreign}, headers=user)
    assert response.status_code == 404
