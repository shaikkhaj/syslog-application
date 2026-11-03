"""Authentication routes for Phase 8.

JWT Bearer token authentication with login rate limiting.
"""

import time
from collections import defaultdict
from typing import Dict, List

from fastapi import APIRouter, Depends, Form, HTTPException, OAuth2PasswordBearer, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import (
    create_access_token,
    decode_access_token,
    get_current_user,
    verify_password,
)
from app.models.models import User
from app.schemas.user import UserRead

router = APIRouter(prefix="/v1", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/login")

# In-memory login rate limiter: key -> list of attempt timestamps.
# Key format: "ip:username" or "ip" for unknown usernames.
_login_attempts: Dict[str, List[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 300  # 5 minutes
_RATE_LIMIT_MAX_ATTEMPTS = 10


def _rate_limit_key(client_host: str | None, username: str | None) -> str:
    host = client_host or "unknown"
    user = username or "unknown"
    return f"{host}:{user}"


def _check_rate_limit(key: str) -> None:
    """Raise HTTP 429 if too many login attempts for the given key."""
    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW
    attempts = _login_attempts[key]
    # Prune old entries
    _login_attempts[key] = [ts for ts in attempts if ts > window_start]
    if len(_login_attempts[key]) >= _RATE_LIMIT_MAX_ATTEMPTS:
        retry_after = int(_RATE_LIMIT_WINDOW - (now - _login_attempts[key][0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )


def _record_attempt(key: str) -> None:
    _login_attempts[key].append(time.time())


def get_current_user_from_token(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> User:
    """FastAPI dependency that retrieves the current user from a JWT Bearer token."""
    try:
        payload = decode_access_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )
        user = get_current_user(db_session=db, username=username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )


@router.post("/login", response_model=UserRead)
def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    request: Request | None = None,
):
    """Authenticate user and return user info with access token.

    Rate-limited per (client_host, username) to mitigate brute-force attacks.
    """
    client_host = request.client.host if request and request.client else None
    key = _rate_limit_key(client_host, username)
    _check_rate_limit(key)

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        _record_attempt(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        _record_attempt(key)
        raise HTTPException(status_code=400, detail="User account is disabled")
    # Successful login clears the rate-limit record for this key.
    _login_attempts.pop(key, None)
    access_token = create_access_token(subject=user.username)
    return {**user.dict(), "access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
def logout() -> dict:
    """Logout the current user."""
    return {"detail": "Successfully logged out"}


@router.get("/me", response_model=UserRead)
def me(
    current_user: User = Depends(get_current_user_from_token),
) -> User:
    """Get current user information."""
    return current_user
