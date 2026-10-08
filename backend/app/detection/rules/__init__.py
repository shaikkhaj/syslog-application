"""Detection rule registry.

``DEFAULT_RULES`` is the single place where rules are registered. To add a
new detection capability: create a module, subclass ``DetectionRule``, and
append an instance below — no pipeline or engine changes required.

Vendor coverage: rules match on the vendor-agnostic classification assigned
at ingestion, with vendor-aware extractors inside each rule (Cisco
``%LINK/%BGP/%OSPF/%SEC_LOGIN`` messages, FortiGate ``devname=/user=``
messages, Juniper ``rpd`` messages, Linux ``sshd/kernel`` messages).
"""

from __future__ import annotations

from app.detection.rules.auth_rules import AuthFailureRule
from app.detection.rules.base import DetectionRule
from app.detection.rules.interface_rules import InterfaceStateRule, LinkFlapRule
from app.detection.rules.performance_rules import PerformanceRule
from app.detection.rules.routing_rules import BgpStateRule, OspfStateRule, RouteChangeRule
from app.detection.rules.system_rules import ConfigChangeRule, DeviceUnreachableRule

DEFAULT_RULES: list[DetectionRule] = [
    InterfaceStateRule(),
    LinkFlapRule(),
    BgpStateRule(),
    OspfStateRule(),
    RouteChangeRule(),
    AuthFailureRule(),
    PerformanceRule(),
    ConfigChangeRule(),
    DeviceUnreachableRule(),
]

__all__ = ["DEFAULT_RULES", "DetectionRule"]
