import csv
import io
from datetime import date


def read_csv(response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.text)))


def test_export_csv(api, client, user, food):
    # EXP-12
    expense = api.create_expense(
        user, food, 12.5, day=date(2026, 6, 1), description='Lunch, "team"', receipt_url="https://example.com/r.png"
    ).json()["expense"]
    api.create_expense(user, food, 99, day=date(2026, 5, 1))  # filtered out below

    response = client.get("/expenses/export", params={"date_from": "2026-06-01"}, headers=user)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert read_csv(response) == [
        ["id", "date", "amount", "currency", "category", "description", "receipt_url"],
        [expense["id"], "2026-06-01", "12.50", "USD", "Food", 'Lunch, "team"', "https://example.com/r.png"],
    ]


def test_export_neutralises_spreadsheet_formulas(api, client, user, food):
    # EXP-12: CSV injection protection.
    api.create_expense(user, food, 1, description='=HYPERLINK("http://evil.example","click")')
    api.create_expense(user, food, 2, description="@SUM(A1:A2)")
    api.create_expense(user, food, 3, description="Normal text")

    descriptions = sorted(row[5] for row in read_csv(client.get("/expenses/export", headers=user))[1:])
    assert descriptions == ["'=HYPERLINK(\"http://evil.example\",\"click\")", "'@SUM(A1:A2)", "Normal text"]


def test_export_requires_auth_and_only_contains_own_data(api, client, user, food):
    # SEC-02
    api.create_expense(user, food, 5)
    assert client.get("/expenses/export").status_code == 401
    other_rows = read_csv(client.get("/expenses/export", headers=api.new_user()))
    assert len(other_rows) == 1  # header only
