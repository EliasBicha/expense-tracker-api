import uuid

import pytest

SYSTEM_NAMES = ["Bills", "Entertainment", "Food", "Health", "Other", "Shopping", "Transport"]


def test_list_contains_system_and_own_categories_only(api, client, user):
    # CAT-01
    other = api.new_user()
    api.create_category(other, "Other User's Category")
    api.create_category(user, "Coffee")

    categories = client.get("/categories", headers=user).json()
    names = [c["name"] for c in categories]
    assert names == SYSTEM_NAMES + ["Coffee"]  # system first, then own, each by name
    assert all(c["is_system"] for c in categories[:7])
    assert not categories[7]["is_system"]


def test_create_category(api, user):
    # CAT-02
    response = api.create_category(user, "  Coffee  ", icon="coffee", color="#6f4e37")
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Coffee"
    assert body["icon"] == "coffee"
    assert body["is_system"] is False


@pytest.mark.parametrize(
    "override",
    [{"name": ""}, {"name": "x" * 51}, {"icon": "Bad Icon!"}, {"color": "red"}, {"color": "#12345"}],
)
def test_create_category_validation(client, user, override):
    # CAT-02
    body = {"name": "Valid", "icon": "valid", "color": "#000000", **override}
    assert client.post("/categories", json=body, headers=user).status_code == 422


@pytest.mark.parametrize("duplicate", ["Coffee", "coffee", "  COFFEE ", "Food", "fOOd"])
def test_duplicate_category_names_are_rejected(api, user, duplicate):
    # CAT-03, D-07: case-insensitive, against own and system categories.
    api.create_category(user, "Coffee")
    response = api.create_category(user, duplicate)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "category_name_taken"


def test_different_users_may_use_the_same_name(api, user):
    # CAT-03
    other = api.new_user()
    assert api.create_category(user, "Coffee").status_code == 201
    assert api.create_category(other, "Coffee").status_code == 201


def test_update_category(api, client, user):
    # CAT-04
    coffee = api.create_category(user, "Coffee").json()
    api.create_category(user, "Tea")

    renamed = client.patch(f"/categories/{coffee['id']}", json={"name": "COFFEE", "color": "#000000"}, headers=user)
    assert renamed.status_code == 200  # changing only the case of its own name is allowed
    assert renamed.json()["name"] == "COFFEE"

    clash = client.patch(f"/categories/{coffee['id']}", json={"name": "tea"}, headers=user)
    assert clash.status_code == 409
    assert client.patch(f"/categories/{coffee['id']}", json={"name": None}, headers=user).status_code == 422
    assert client.patch(f"/categories/{coffee['id']}", json={"icon": "Bad Icon!"}, headers=user).status_code == 422
    assert client.patch(f"/categories/{coffee['id']}", json={"color": "red"}, headers=user).status_code == 422


def test_system_categories_are_read_only(api, client, user, food):
    # CAT-05
    for response in (
        client.patch(f"/categories/{food}", json={"name": "Groceries"}, headers=user),
        client.delete(f"/categories/{food}", headers=user),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "system_category_readonly"


def test_other_users_categories_are_not_found(api, client, user):
    # CAT-06, EXP-02, BUD-02, D-06: indistinguishable from a non-existent id.
    foreign = api.create_category(api.new_user(), "Private").json()["id"]
    for category_id in (foreign, str(uuid.uuid4())):
        assert client.patch(f"/categories/{category_id}", json={"name": "Mine"}, headers=user).status_code == 404
        assert client.delete(f"/categories/{category_id}", headers=user).status_code == 404
        assert api.create_expense(user, category_id, 10).status_code == 404
        assert api.set_budget(user, category_id, 100).status_code == 404


def test_delete_category_with_expenses_returns_count(api, client, user):
    # CAT-07
    coffee = api.create_category(user, "Coffee").json()["id"]
    api.create_expense(user, coffee, 3.5)
    api.create_expense(user, coffee, 4)

    response = client.delete(f"/categories/{coffee}", headers=user)
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "category_in_use"
    assert error["details"] == {"expense_count": 2}
    assert "Move them to another category" in error["message"]


def test_delete_unused_category_also_removes_its_budgets(api, client, user):
    # CAT-08
    coffee = api.create_category(user, "Coffee").json()["id"]
    api.set_budget(user, coffee, 50)

    assert client.delete(f"/categories/{coffee}", headers=user).status_code == 204
    assert client.get("/budgets", headers=user).json() == []
    assert coffee not in [c["id"] for c in client.get("/categories", headers=user).json()]
