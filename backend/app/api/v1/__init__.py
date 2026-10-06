"""Version 1 API router."""

from fastapi import APIRouter

from app.api.v1 import devices, events, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(events.router)
api_router.include_router(devices.router)
