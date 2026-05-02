"""Telemetry sources — anything that produces a stream of TelemetrySample objects."""
from .base import TelemetrySource
from .outgauge import OutGaugeSource, OutGaugePacket

__all__ = ["TelemetrySource", "OutGaugeSource", "OutGaugePacket"]
