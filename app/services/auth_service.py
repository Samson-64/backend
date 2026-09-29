from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import JWTError, jwt
import calendar
import hashlib
import secrets
from sqlalchemy.orm import Session
from app.config import get_settings
from app.models.refresh_token import RefreshToken
from app.models.user import User

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Stand-in for "no expiry" on the NOT NULL refresh_tokens.expires_at column.
# 9999-12-31 23:59:59 is the maximum MySQL DATETIME value, so the existing
# `expires_at > now` filter in verify_refresh_token simply always passes.
NEVER_EXPIRES = datetime(9999, 12, 31, 23, 59, 59)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str) -> str:
    issued_at = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": issued_at,
    }
    # When configured never to expire, the "exp" claim is omitted entirely.
    # python-jose's _validate_exp returns early when "exp" is absent, so a token
    # without it is accepted forever and no decode-side flag is needed.
    if not settings.access_token_never_expires:
        payload["exp"] = issued_at + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token_claims(token: str) -> dict | None:
    """Return the full decoded JWT payload, or None if it is not valid."""
    try:
        return jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None


def decode_access_token(token: str) -> str | None:
    claims = decode_access_token_claims(token)
    return None if claims is None else claims.get("sub")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _purge_dead_refresh_tokens(db: Session) -> None:
    """Drop refresh tokens that can never be used again.

    When refresh tokens are configured never to expire, their 7-day lifetime is
    no longer the implicit cleanup mechanism, and because /auth/refresh rotates
    the token on every call a long-lived session would otherwise insert an
    unbounded number of rows. Revoked rows and rows past their expiry are dead
    weight, so drop them whenever a new token is issued.
    """
    now = datetime.now(timezone.utc)
    db.query(RefreshToken).filter(
        (RefreshToken.revoked == True) | (RefreshToken.expires_at < now)
    ).delete(synchronize_session=False)
    db.commit()


def create_refresh_token(user_id: str, db: Session) -> str:
    token = secrets.token_urlsafe(64)
    token_hash = _hash_token(token)
    if settings.refresh_token_never_expires:
        expires_at = NEVER_EXPIRES
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

    db_token = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(db_token)
    db.commit()
    _purge_dead_refresh_tokens(db)
    return token


def verify_refresh_token(token: str, db: Session) -> str | None:
    token_hash = _hash_token(token)
    db_token = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )
    if db_token:
        return db_token.user_id
    return None


def revoke_refresh_token(token: str, db: Session) -> bool:
    token_hash = _hash_token(token)
    db_token = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if db_token:
        db_token.revoked = True
        db.commit()
        return True
    return False


def revoke_all_user_tokens(user_id: str, db: Session) -> None:
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked == False,
    ).update({"revoked": True})
    db.commit()


def _to_epoch(value: datetime) -> int:
    """Seconds since the epoch for a naive-UTC datetime read back from MySQL."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return calendar.timegm(value.timetuple())


def revoke_user_access_tokens(user: User, db: Session) -> None:
    """Invalidate every access token already issued to this user.

    Access tokens are stateless and, when configured never to expire, could not
    otherwise be killed by a logout. Recording a cutoff timestamp on the user
    lets get_current_user reject any token minted before it, without needing a
    per-token blacklist or an extra query (it already loads the same row).
    """
    user.tokens_valid_after = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(user)
    db.commit()


def is_token_revoked(user: User, claims: dict) -> bool:
    """True when the token described by `claims` was minted before logout."""
    cutoff = user.tokens_valid_after
    if cutoff is None:
        return False
    issued_at = claims.get("iat")
    if not isinstance(issued_at, (int, float)):
        # No usable "iat" to compare against, so fall back to the strictest
        # reading and treat the token as revoked.
        return True
    # "<=" rather than "<" because tokens_valid_after is a MySQL DATETIME, which
    # stores whole seconds: the cutoff and a token minted in the same second are
    # indistinguishable, and failing closed means a logout can never leave a
    # live token behind. The cost is that a re-login in that same second is
    # rejected once and has to be retried.
    return int(issued_at) <= _to_epoch(cutoff)
