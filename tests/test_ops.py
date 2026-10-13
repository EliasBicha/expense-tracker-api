"""Operational requirements: health check, configuration safety, request logging."""

import logging

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_health_reports_ok_without_authentication(client):
    # OPS-01
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_jwt_secret_shorter_than_32_characters_is_refused():
    # SEC-01: the app can't start with a weak signing secret.
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+psycopg://u:p@localhost/db", jwt_secret="x" * 31)
    assert Settings(database_url="postgresql+psycopg://u:p@localhost/db", jwt_secret="x" * 32)


def test_request_id_is_echoed_and_logged(client, user, caplog):
    # LOG-01: one structured log line per request, with request id and user id.
    caplog.set_level(logging.INFO, logger="app.request")
    response = client.get("/users/me", headers={**user, "X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"

    fields = [record for record in caplog.records if record.name == "app.request"][-1].fields
    assert fields["request_id"] == "abc-123"
    assert fields["method"] == "GET"
    assert fields["path"] == "/users/me"
    assert fields["status"] == 200
    assert fields["user_id"] == response.json()["id"]


def test_unsafe_request_id_is_replaced(client):
    # LOG-01: a client-supplied id that is too long or has odd characters isn't trusted.
    for unsafe in ("x" * 65, "has spaces", "semi;colon"):
        echoed = client.get("/health", headers={"X-Request-ID": unsafe}).headers["X-Request-ID"]
        assert echoed != unsafe
        assert len(echoed) == 32  # a generated uuid4 hex
