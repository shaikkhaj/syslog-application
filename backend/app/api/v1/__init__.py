"""Version 1 API router."""

from fastapi import APIRouter

from app.api.v1 import alerts, devices, events, health, incidents, ws

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(events.router)
api_router.include_router(devices.router)
api_router.include_router(alerts.router)
api_router.include_router(incidents.router)
api_router.include_router(ws.router)
