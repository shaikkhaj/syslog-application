"""Base class for detection rules.

Adding a new rule = create a module, subclass :class:`DetectionRule`, and
append an instance to ``DEFAULT_RULES`` in ``app.detection.rules`` — the
pipeline and engine never change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from sqlalchemy.orm import Session

from app.detection.config import DetectionConfig
from app.detection.types import DetectionResult, EventType
from app.models.models import SyslogEvent


class DetectionRule(ABC):
    """A single detection concern (one rule = one kind of finding).

    Attributes:
        name: Stable rule identifier stored on every alert it raises.
        event_types: Event classifications this rule reacts to (None = all).
        vendors: Restrict to these vendors (None = all vendors).
    """

    name: str = "rule"
    event_types: frozenset[EventType] | None = None
    vendors: frozenset[str] | None = None

    def applies_to(self, event: SyslogEvent) -> bool:
        """Return True when this rule should evaluate the given event."""
        if self.event_types is not None:
            if event.event_type_code not in {t.value for t in self.event_types}:
                return False
        if self.vendors is not None and event.vendor not in self.vendors:
            return False
        return True

    @abstractmethod
    def evaluate(
        self,
        event: SyslogEvent,
        db: Session,
        config: DetectionConfig,
    ) -> Iterable[DetectionResult]:
        """Inspect one stored event and return zero or more findings."""

    # Helpers shared by concrete rules -------------------------------------

    @staticmethod
    def _host(event: SyslogEvent) -> str:
        return event.hostname or event.source_ip

    @staticmethod
    def _device_part(event: SyslogEvent) -> str:
        return str(event.device_id) if event.device_id else event.source_ip
