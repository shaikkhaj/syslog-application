"""WebSocket endpoint streaming real-time alert updates.

Clients must pass a valid JWT Bearer token as a query parameter:
    ws://host/api/v1/ws/alerts?token=<access_token>

The token is verified against the same JWT secret used by the REST API.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.models import User
from app.realtime.broadcaster import alert_broadcaster

logger = logging.getLogger(__name__)
router = APIRouter(tags=["realtime"])


async def _get_current_user_ws(token: str) -> User:
    """Validate a JWT token for a WebSocket connection and return the user."""
    from fastapi import HTTPException

    try:
        payload = decode_access_token(token)
        username: str | None = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        return user
    finally:
        db.close()


@router.websocket("/ws/alerts")
async def stream_alerts(websocket: WebSocket, token: str | None = None) -> None:
    """Push alert JSON frames to authenticated WebSocket subscribers.

    Requires a valid JWT Bearer token passed as ``?token=`` query parameter.
    Connections without a valid token are closed with code 4003.
    """
    if token is None:
        await websocket.close(code=4003)
        return

    try:
        _get_current_user_ws(token)
    except Exception:
        await websocket.close(code=4003)
        return

    await websocket.accept()
    queue = alert_broadcaster.subscribe()
    try:
        await websocket.send_json(
            {"type": "connected", "subscribers": alert_broadcaster.subscriber_count}
        )
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:  # pragma: no cover - client vanished mid-send
        logger.debug("Alert websocket closed unexpectedly", exc_info=True)
    finally:
        alert_broadcaster.unsubscribe(queue)
