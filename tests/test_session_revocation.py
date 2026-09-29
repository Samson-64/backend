"""Logout must actually end the session, since tokens no longer expire."""

import time
from datetime import datetime, timedelta, timezone

from app.models.user import User
from app.services.auth_service import (
    create_access_token,
    decode_access_token_claims,
    is_token_revoked,
)

from conftest import TEST_PASSWORD

AUTH = "/api/auth"


def _login(client):
    response = client.post(
        f"{AUTH}/login",
        json={"email": "test@example.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _bearer(body):
    return {"Authorization": f"Bearer {body['access_token']}"}


def test_login_returns_a_working_session(client, user):
    body = _login(client)
    response = client.get(f"{AUTH}/me", headers=_bearer(body))
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


def test_logout_invalidates_the_access_token(client, user):
    body = _login(client)

    response = client.post(
        f"{AUTH}/logout", json={"refresh_token": body["refresh_token"]}, headers=_bearer(body)
    )
    assert response.status_code == 200

    # The token itself is still cryptographically valid and has no exp, so this
    # only passes because of the tokens_valid_after cutoff.
    response = client.get(f"{AUTH}/me", headers=_bearer(body))
    assert response.status_code == 401
    assert "sign in again" in response.json()["detail"]


def test_logout_revokes_the_refresh_token(client, user):
    body = _login(client)
    client.post(
        f"{AUTH}/logout", json={"refresh_token": body["refresh_token"]}, headers=_bearer(body)
    )

    response = client.post(f"{AUTH}/refresh", json={"refresh_token": body["refresh_token"]})
    assert response.status_code == 401


def test_logout_all_invalidates_the_access_token(client, user):
    body = _login(client)
    assert client.post(f"{AUTH}/logout-all", headers=_bearer(body)).status_code == 200

    response = client.get(f"{AUTH}/me", headers=_bearer(body))
    assert response.status_code == 401


def test_logging_in_again_after_logout_works(client, user, db):
    first = _login(client)
    client.post(
        f"{AUTH}/logout", json={"refresh_token": first["refresh_token"]}, headers=_bearer(first)
    )
    # tokens_valid_after has one-second resolution, and a token issued at that
    # same second is rejected, so cross the boundary before signing back in.
    time.sleep(1.1)

    second = _login(client)
    assert second["access_token"] != first["access_token"]

    response = client.get(f"{AUTH}/me", headers=_bearer(second))
    assert response.status_code == 200


def test_refresh_issues_a_token_that_still_works(client, user):
    body = _login(client)
    response = client.post(f"{AUTH}/refresh", json={"refresh_token": body["refresh_token"]})
    assert response.status_code == 200

    response = client.get(f"{AUTH}/me", headers=_bearer(response.json()))
    assert response.status_code == 200


def test_refresh_after_logout_then_relogin_is_still_dead(client, user):
    """A token rotated out before logout must not be resurrected by a refresh."""
    first = _login(client)
    client.post(
        f"{AUTH}/logout", json={"refresh_token": first["refresh_token"]}, headers=_bearer(first)
    )

    response = client.post(f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]})
    assert response.status_code == 401


def test_user_without_tokens_valid_after_is_not_revoked(db, user):
    claims = decode_access_token_claims(create_access_token(user.id))
    assert is_token_revoked(user, claims) is False


def test_token_issued_before_logout_is_revoked(db, user):
    stale_claims = decode_access_token_claims(create_access_token(user.id))
    user.tokens_valid_after = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        seconds=1
    )
    db.add(user)
    db.commit()
    assert is_token_revoked(user, stale_claims) is True


def test_token_issued_after_logout_is_accepted(db, user):
    user.tokens_valid_after = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        seconds=1
    )
    db.add(user)
    db.commit()
    fresh_claims = decode_access_token_claims(create_access_token(user.id))
    assert is_token_revoked(user, fresh_claims) is False


def test_token_without_iat_is_treated_as_revoked(db, user):
    user.tokens_valid_after = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(user)
    db.commit()
    assert is_token_revoked(user, {"sub": user.id}) is True


def test_websocket_handshake_honours_logout(db, user, monkeypatch):
    from app.routers import realtime

    monkeypatch.setattr(realtime, "SessionLocal", lambda: db)
    token = create_access_token(user.id)
    assert realtime._authenticate_socket(token) == user.id

    user.tokens_valid_after = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        seconds=1
    )
    db.add(user)
    db.commit()
    assert realtime._authenticate_socket(token) is None


def test_websocket_handshake_rejects_bad_tokens(db, monkeypatch):
    from app.routers import realtime

    monkeypatch.setattr(realtime, "SessionLocal", lambda: db)
    assert realtime._authenticate_socket("") is None
    assert realtime._authenticate_socket("not-a-jwt") is None
    assert realtime._authenticate_socket(create_access_token("ghost-user")) is None
