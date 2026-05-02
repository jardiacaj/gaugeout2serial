"""Aggregate device autodiscovery."""
from __future__ import annotations

from typing import List, Type

from .base import Device


def all_device_classes() -> List[Type[Device]]:
    """Registered device classes. New devices are appended here."""
    from .moza_r5.device import MozaR5
    return [MozaR5]


def auto_discover_devices(device_classes: List[Type[Device]] | None = None) -> List[Device]:
    """Run discover() on each registered device class, return aggregated list."""
    if device_classes is None:
        device_classes = all_device_classes()
    out: List[Device] = []
    for cls in device_classes:
        out.extend(cls.discover())
    return out
