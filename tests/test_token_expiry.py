"""Token issuance: never-expiring by default, still honouring a positive value."""

import time
from datetime import datetime, timedelta

import pytest
from jose import jwt

from app.services import auth_service
from app.services.auth_service import (
    NEVER_EXPIRES,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_access_token_claims,
    verify_refresh_token,
)


def test_access_token_omits_exp_when_never_expiring():
    claims = decode_access_token_claims(create_access_token("user-1"))
    assert claims is not None
    # python-jose's _validate_exp returns early when "exp" is absent, which is
    # what makes the token valid forever.
    assert "exp" not in claims
    assert claims["sub"] == "user-1"


def test_access_token_still_works_with_no_exp_claim():
    assert decode_access_token(create_access_token("user-1")) == "user-1"


def test_access_token_carries_exp_when_configured(monkeypatch):
    monkeypatch.setattr(auth_service.settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 30)
    claims = decode_access_token_claims(create_access_token("user-1"))
    assert claims is not None
    assert "exp" in claims
    assert claims["exp"] - claims["iat"] == pytest.approx(30 * 60, abs=5)


def test_explicitly_expired_token_is_rejected(monkeypatch):
    """Expiry validation still works, it is just not applied to our own tokens."""
    now = int(time.time())
    stale = jwt.encode(
        {"sub": "user-1", "iat": now - 7200, "exp": now - 3600},
        auth_service.settings.JWT_SECRET_KEY,
        algorithm=auth_service.settings.JWT_ALGORITHM,
    )
    assert decode_access_token(stale) is None


def test_token_signed_with_another_key_is_rejected():
    foreign = jwt.encode(
        {"sub": "user-1", "iat": int(time.time())},
        "a-different-secret",
        algorithm=auth_service.settings.JWT_ALGORITHM,
    )
    assert decode_access_token(foreign) is None


def test_refresh_token_uses_never_expires_sentinel(db):
    token = create_refresh_token("user-1", db)
    row = db.query(auth_service.RefreshToken).one()
    assert row.expires_at == NEVER_EXPIRES
    assert verify_refresh_token(token, db) == "user-1"


def test_refresh_token_carries_expiry_when_configured(db, monkeypatch):
    monkeypatch.setattr(auth_service.settings, "REFRESH_TOKEN_EXPIRE_DAYS", 7)
    create_refresh_token("user-1", db)
    row = db.query(auth_service.RefreshToken).one()
    assert row.expires_at != NEVER_EXPIRES
    # Should land roughly a week out, not at the sentinel.
    assert NEVER_EXPIRES - row.expires_at > timedelta(days=6)


def test_decode_rejects_garbage_token():
    assert decode_access_token("not-a-jwt") is None
    assert decode_access_token_claims("not-a-jwt") is None


def test_purge_drops_revoked_and_expired_rows(db):
    from app.models.refresh_token import RefreshToken

    live = create_refresh_token("user-1", db)
    revoked = create_refresh_token("user-1", db)
    auth_service.revoke_refresh_token(revoked, db)
    db.add(
        RefreshToken(
            user_id="user-1",
            token_hash="deadbeef",
            expires_at=datetime(2000, 1, 1),
        )
    )
    db.commit()
    assert db.query(RefreshToken).count() == 3

    # Issuing another token triggers the purge.
    create_refresh_token("user-1", db)

    remaining = {row.token_hash for row in db.query(RefreshToken).all()}
    assert auth_service._hash_token(live) in remaining
    assert auth_service._hash_token(revoked) not in remaining
    assert "deadbeef" not in remaining
