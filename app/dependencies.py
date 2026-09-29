from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.services.auth_service import decode_access_token_claims, is_token_revoked
from app.models.user import User

security = HTTPBearer()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    claims = decode_access_token_claims(token)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    # Access tokens no longer expire on their own, so a token minted before the
    # user's last logout is rejected here instead. The User row is already
    # loaded, so this costs no extra query.
    if is_token_revoked(user, claims):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session ended, please sign in again",
        )
    return user


def require_staff(user: User = Depends(get_current_user)) -> User:
    if user.role.value != "STAFF":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff access required",
        )
    return user


def require_specialist(user: User = Depends(get_current_user)) -> User:
    if user.role.value != "SPECIALIST":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Specialist access required",
        )
    if not user.person_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Specialist account is not linked to a specialist profile",
        )
    return user
