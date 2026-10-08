"""WebSocket endpoint streaming real-time alert updates."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime.broadcaster import alert_broadcaster

logger = logging.getLogger(__name__)
router = APIRouter(tags=["realtime"])


@router.websocket("/ws/alerts")
async def stream_alerts(websocket: WebSocket) -> None:
    """Push ``{"type": "alert", "action": "created"|"updated", ...}`` frames.

    Auth is introduced in a later phase together with RBAC.
    """
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
