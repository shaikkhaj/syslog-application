"""Topology graph and link CRUD (Phase 4).

The graph endpoint derives highlighting from existing data:
open alerts (status != resolved) and active incidents mark nodes/links as
``affected`` and carry the maximum severity for colouring. The underlying
aggregations are shared with Phase 5 health/RCA via ``app.health.queries``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.detection.types import AlertSeverity
from app.health.queries import active_incidents_by_device, open_alerts_by_device
from app.models.models import Device, TopologyLink
from app.schemas.topology import (
    LinkCreate,
    LinkUpdate,
    TopologyLinkOut,
    TopologyNodeOut,
    TopologyResponse,
)

router = APIRouter(tags=["topology"])

_SEVERITY_ORDER = [s.value for s in AlertSeverity]


def _max_severity(severities: list[str | None]) -> str | None:
    ranked = [s for s in severities if s in _SEVERITY_ORDER]
    if not ranked:
        return None
    return max(ranked, key=lambda value: _SEVERITY_ORDER.index(value))


@router.get(
    "/topology",
    response_model=TopologyResponse,
    summary="Topology graph with alert/incident highlighting",
)
def get_topology(db: Session = Depends(get_db)) -> TopologyResponse:
    devices = list(db.execute(select(Device)).scalars().all())
    links = list(db.execute(select(TopologyLink)).scalars().all())
    alerts_by_device = open_alerts_by_device(db)
    incidents_by_device = active_incidents_by_device(db)

    nodes: list[TopologyNodeOut] = []
    for device in devices:
        alert_info = alerts_by_device.get(
            device.id, {"count": 0, "severities": [], "interfaces": set()}
        )
        incident_severities = incidents_by_device.get(device.id, [])
        severity = _max_severity(alert_info["severities"] + incident_severities)
        nodes.append(
            TopologyNodeOut(
                id=device.id,
                hostname=device.hostname,
                ip_address=device.ip_address,
                vendor=device.vendor,
                device_type=device.device_type or "router",
                status=device.status,
                last_seen_at=device.last_seen_at,
                affected=bool(alert_info["count"] or incident_severities),
                open_alert_count=alert_info["count"],
                open_incident_count=len(incident_severities),
                max_severity=severity,
            )
        )

    node_severity = {node.id: node.max_severity for node in nodes}
    node_affected = {node.id: node.affected for node in nodes}
    link_outs: list[TopologyLinkOut] = []
    for link in links:
        side_severities = [
            node_severity.get(link.source_device_id),
            node_severity.get(link.target_device_id),
        ]
        interface_hit = False
        for device_id, interface in (
            (link.source_device_id, link.source_interface),
            (link.target_device_id, link.target_interface),
        ):
            info = alerts_by_device.get(device_id)
            if info and interface in info["interfaces"]:
                interface_hit = True
                if info["severities"]:
                    side_severities.append(
                        max(
                            info["severities"],
                            key=lambda value: _SEVERITY_ORDER.index(value),
                        )
                    )
        affected = (
            node_affected.get(link.source_device_id, False)
            or node_affected.get(link.target_device_id, False)
            or interface_hit
        )
        link_outs.append(
            TopologyLinkOut(
                id=link.id,
                source_device_id=link.source_device_id,
                source_interface=link.source_interface,
                target_device_id=link.target_device_id,
                target_interface=link.target_interface,
                status=link.status,
                affected=affected,
                max_severity=_max_severity(side_severities),
                created_at=link.created_at,
                updated_at=link.updated_at,
            )
        )
    return TopologyResponse(nodes=nodes, links=link_outs)


def _get_link_or_404(link_id: int, db: Session) -> TopologyLink:
    link = db.get(TopologyLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    return link


def _require_devices(source_id: int, target_id: int, db: Session) -> None:
    if source_id == target_id:
        raise HTTPException(
            status_code=422, detail="A link cannot connect a device to itself"
        )
    for device_id in {source_id, target_id}:
        if db.get(Device, device_id) is None:
            raise HTTPException(
                status_code=404, detail=f"Device {device_id} not found"
            )


@router.post(
    "/links",
    response_model=TopologyLinkOut,
    status_code=201,
    summary="Create an interface-to-interface link",
)
def create_link(payload: LinkCreate, db: Session = Depends(get_db)) -> TopologyLink:
    _require_devices(payload.source_device_id, payload.target_device_id, db)
    link = TopologyLink(**payload.model_dump())
    db.add(link)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Link already exists")
    db.refresh(link)
    return link


@router.patch(
    "/links/{link_id}", response_model=TopologyLinkOut, summary="Edit a link"
)
def update_link(
    link_id: int, payload: LinkUpdate, db: Session = Depends(get_db)
) -> TopologyLink:
    link = _get_link_or_404(link_id, db)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(link, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Link already exists")
    db.refresh(link)
    return link


@router.delete("/links/{link_id}", status_code=204, summary="Delete a link")
def delete_link(link_id: int, db: Session = Depends(get_db)):
    link = _get_link_or_404(link_id, db)
    db.delete(link)
    db.commit()
