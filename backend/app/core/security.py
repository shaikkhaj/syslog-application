"""Security module — authentication, authorization, and password handling.

This module provides:
- Password hashing and verification using bcrypt
- JWT token creation and decoding
- FastAPI dependency injection for current user / superuser retrieval
- Permission-based authorization

The functions are designed to be standalone (no module-level Depends imports),
callers wrap with Depends() as needed.
"""
import bcrypt
from typing import Optional, Dict, Any

from jose import JWTError, jwt as jwt_encode

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.models import User


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False
def create_access_token(
    subject: str,
    expires_delta: Optional[float] = None,
) -> str:
    """Create a JWT access token for the given subject."""
    from datetime import datetime, timedelta, timezone

    if expires_delta:
        expire = datetime.now(timezone.utc) + timedelta(seconds=expires_delta)
    else:
        minutes = getattr(settings, "access_token_expire_minutes", 30)
        expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    to_encode = {"sub": subject, "exp": expire, "iat": datetime.now(timezone.utc)}
    encoded = jwt_encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    return encoded


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode a JWT access token and return its payload."""
    from jose import jwt as jwt_decode

    payload = jwt_decode(
        token,
        settings.secret_key,
        algorithms=[settings.algorithm],
    )
    return payload

def get_db():
    """Dependency that provides a SQLAlchemy DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    db_session: Any = ...,
    username: str = ...,
) -> User:
    """Dependency that retrieves the current user from the database."""
    from fastapi import HTTPException

    user = db_session.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
def get_current_active_user(
    db_session: Any = ...,
    username: str = ...,
) -> User:
    """Dependency that retrieves the current active user from the database."""
    from fastapi import HTTPException

    user = db_session.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


def get_current_active_superuser(
    db_session: Any = ...,
    username: str = ...,
) -> User:
    """Dependency that retrieves the current active superuser."""
    from fastapi import HTTPException

    user = db_session.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    if user.role != "superuser" and not getattr(user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return user
def authorize_permission(
    required_role: str = "superuser",
) -> Any:
    """FastAPI dependency that authorizes a user for a given role."""
    from fastapi import HTTPException

    def _checker(
        db: Any = ...,
        current_user: User = ...,
    ) -> User:
        # Superuser bypass
        if getattr(current_user, "is_superuser", False) or current_user.role == required_role:
            return current_user
        raise HTTPException(
            status_code=403,
            detail=f"User does not have required role: {required_role}",
        )

    return _checker