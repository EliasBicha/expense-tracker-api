def test_update_profile(client, user):
    # USR-02
    response = client.patch(
        "/users/me", json={"display_name": "  New Name ", "default_currency": "EUR"}, headers=user
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "New Name"
    assert response.json()["default_currency"] == "EUR"
    assert client.get("/users/me", headers=user).json()["default_currency"] == "EUR"


def test_update_profile_rejects_null_and_other_fields(client, user):
    # USR-02, D-13: only display_name and default_currency, and not null.
    for body in ({"display_name": None}, {"email": "new@example.com"}, {"password_hash": "x"}):
        assert client.patch("/users/me", json=body, headers=user).status_code == 422


def test_currency_change_blocked_once_expenses_exist(api, client, user, food):
    # USR-03, D-05
    api.create_expense(user, food, 10)
    response = client.patch("/users/me", json={"default_currency": "EUR"}, headers=user)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "currency_change_blocked"

    # Re-sending the current currency, or changing only the name, is fine.
    assert client.patch("/users/me", json={"default_currency": "USD"}, headers=user).status_code == 200
    assert client.patch("/users/me", json={"display_name": "Still OK"}, headers=user).status_code == 200


def test_currency_change_blocked_once_budgets_exist(api, client, user, food):
    # USR-03, D-05: budget amounts are in the user's currency too, so a budget alone blocks it.
    budget_id = api.set_budget(user, food, 500).json()["id"]
    response = client.patch("/users/me", json={"default_currency": "EUR"}, headers=user)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "currency_change_blocked"
    assert client.get("/users/me", headers=user).json()["default_currency"] == "USD"

    # With neither expenses nor budgets left, the change is allowed again.
    client.delete(f"/budgets/{budget_id}", headers=user)
    assert client.patch("/users/me", json={"default_currency": "EUR"}, headers=user).status_code == 200
