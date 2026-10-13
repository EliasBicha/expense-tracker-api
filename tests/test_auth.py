import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import User
from app.services import users as user_service


def test_register_login_and_get_profile(api, client):
    # AUTH-01, AUTH-04, USR-01
    registered = api.register(email="alice@example.com", default_currency="ILS")
    assert registered.status_code == 201
    profile = registered.json()
    assert profile["email"] == "alice@example.com"
    assert profile["default_currency"] == "ILS"

    login = api.login("alice@example.com")
    assert login.status_code == 200
    body = login.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().jwt_expire_minutes * 60

    me = client.get("/users/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json() == profile


def test_email_is_case_insensitive_and_unique(api):
    # AUTH-02
    assert api.register(email="Bob@Example.com").json()["email"] == "bob@example.com"
    duplicate = api.register(email="BOB@example.COM")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "email_taken"
    assert api.login("bOb@example.com").status_code == 200


@pytest.mark.parametrize(
    "override, field",
    [
        ({"email": "not-an-email"}, "email"),
        ({"password": "short"}, "password"),
        ({"password": "x" * 129}, "password"),
        ({"display_name": "   "}, "display_name"),
        ({"default_currency": "BTC"}, "default_currency"),
        ({"is_admin": True}, "is_admin"),
    ],
)
def test_register_validation(client, override, field):
    # AUTH-02, AUTH-03, D-13, D-14
    body = {"email": "v@example.com", "password": "correct-horse-1", "display_name": "V", **override}
    response = client.post("/auth/register", json=body)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert field in [detail["field"] for detail in error["details"]]


def test_password_is_hashed_and_never_returned(api, client, db_session):
    # AUTH-03, SEC-03
    password = "MySecret-Passw0rd"
    response = api.register(email="carol@example.com", password=password)
    assert password not in response.text
    assert "password" not in response.json()

    stored = db_session.scalar(select(User).where(User.email == "carol@example.com"))
    assert stored.password_hash.startswith("$argon2id$")
    assert password not in stored.password_hash


def test_validation_errors_do_not_echo_submitted_values(client):
    # SEC-03: FastAPI's default 422 would include the rejected password as "input".
    response = client.post(
        "/auth/register",
        json={"email": "d@example.com", "password": "Sh0rt!", "display_name": "D"},
    )
    assert response.status_code == 422
    assert "Sh0rt!" not in response.text


def test_wrong_password_and_unknown_email_are_indistinguishable(api):
    # AUTH-05
    api.register(email="dave@example.com")
    wrong_password = api.login("dave@example.com", "wrong-password")
    unknown_email = api.login("nobody@example.com", "wrong-password")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_login_with_malformed_email_is_an_ordinary_failed_login(api):
    # AUTH-05: not a 422 that would reveal anything about validation.
    response = api.login("not-an-email", "whatever-password")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_unknown_email_still_performs_a_hash_check(api, monkeypatch):
    # AUTH-05: equal work for unknown emails, so timing doesn't reveal registered accounts.
    calls = []
    monkeypatch.setattr(user_service, "verify_dummy_password", lambda password: calls.append(password))
    api.login("ghost@example.com", "some-password")
    assert calls == ["some-password"]


def _token(secret: str, **claims) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(uuid.uuid4()), "iat": now, "exp": now + timedelta(minutes=5), **claims}
    return jwt.encode(payload, secret, algorithm="HS256")


def _real_user_id(api, client) -> str:
    headers = api.new_user()
    return client.get("/users/me", headers=headers).json()["id"]


@pytest.mark.parametrize(
    "make_header",
    [
        lambda uid: None,
        lambda uid: "Bearer not-a-jwt",
        lambda uid: "Basic dXNlcjpwYXNz",
        # expired
        lambda uid: "Bearer " + _token(get_settings().jwt_secret, sub=uid, exp=datetime.now(UTC) - timedelta(seconds=1)),
        # signed with a different secret
        lambda uid: "Bearer " + _token("another-secret-that-is-long-enough-123456", sub=uid),
        # unsigned token ("alg": "none")
        lambda uid: "Bearer " + jwt.encode({"sub": uid, "iat": 0, "exp": 9999999999}, None, algorithm="none"),
        # valid signature, but the user doesn't exist
        lambda uid: "Bearer " + _token(get_settings().jwt_secret),
    ],
    ids=["missing", "garbage", "wrong-scheme", "expired", "wrong-secret", "alg-none", "unknown-user"],
)
def test_protected_endpoints_reject_invalid_tokens(api, client, make_header):
    # AUTH-06, AUTH-07
    header = make_header(_real_user_id(api, client))
    headers = {"Authorization": header} if header else {}
    response = client.get("/users/me", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.headers["WWW-Authenticate"] == "Bearer"
