"""Topology graph and link CRUD (Phase 4).

The graph endpoint derives highlighting from existing data:
open alerts (status != resolved) and active incidents mark nodes/links as
``affected`` and carry the maximum severity for colouring.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.correlation.engine import ACTIVE_STATUSES
from app.db.session import get_db
from app.detection.types import AlertSeverity
from app.models.models import Alert, Device, Incident, TopologyLink
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


def _open_alerts(db: Session) -> dict[int, dict]:
    """Open (non-resolved) alerts grouped by device id."""
    alerts = (
        db.execute(select(Alert).where(Alert.status != "resolved")).scalars().all()
    )
    grouped: dict[int, dict] = {}
    for alert in alerts:
        if alert.device_id is None:
            continue
        entry = grouped.setdefault(
            alert.device_id, {"count": 0, "severities": [], "interfaces": set()}
        )
        entry["count"] += 1
        entry["severities"].append(alert.severity)
        interface = (alert.context or {}).get("interface")
        if interface:
            entry["interfaces"].add(str(interface))
    return grouped


def _active_incidents(db: Session) -> dict[int, list[str]]:
    """Active incident severities grouped by affected device id."""
    incidents = (
        db.execute(select(Incident).where(Incident.status.in_(ACTIVE_STATUSES)))
        .scalars()
        .all()
    )
    grouped: dict[int, list[str]] = {}
    for incident in incidents:
        device_ids = {incident.device_id}
        for entry in incident.affected_devices or []:
            if entry.get("device_id"):
                device_ids.add(entry["device_id"])
        for device_id in device_ids:
            if device_id:
                grouped.setdefault(device_id, []).append(incident.severity)
    return grouped


@router.get(
    "/topology",
    response_model=TopologyResponse,
    summary="Topology graph with alert/incident highlighting",
)
def get_topology(db: Session = Depends(get_db)) -> TopologyResponse:
    devices = list(db.execute(select(Device)).scalars().all())
    links = list(db.execute(select(TopologyLink)).scalars().all())
    alerts_by_device = _open_alerts(db)
    incidents_by_device = _active_incidents(db)

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
