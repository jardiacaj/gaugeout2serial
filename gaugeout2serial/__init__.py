"""
gaugeout2serial — bridge sim telemetry to serial-attached racing-wheel dashes.

Architecture:
    sources.*  → produce TelemetrySample objects (currently OutGauge UDP)
    devices.*  → consume TelemetrySample / DeviceState (currently Moza R5)
    bridge     → wires a source to one or more devices and runs the loop
"""
from __future__ import annotations

__version__ = "0.2.0"

from .bridge import Bridge
from .cli import main
from .devices.base import Device, DeviceState
from .devices.discovery import all_device_classes, auto_discover_devices
from .devices.moza_r5.device import MozaR5
from .sources.base import TelemetrySource
from .sources.outgauge import OutGaugeFlag, OutGaugePacket, OutGaugeSource
from .telemetry import TelemetrySample

__all__ = [
    "__version__",
    "main",
    "Bridge",
    "TelemetrySample",
    "TelemetrySource",
    "OutGaugeSource", "OutGaugePacket", "OutGaugeFlag",
    "Device", "DeviceState",
    "auto_discover_devices", "all_device_classes",
    "MozaR5",
]
