"""
gaugeout2serial — bridge OutGauge UDP telemetry to a Moza R5 dash over serial.
"""
from __future__ import annotations

__version__ = "0.1.0"

from .protocol import (
    frame, indicator_mode_frame, rpm_mode_frame, telemetry_frame,
    build_bitmask, single_led_mask,
    NO_DATA_PAYLOAD, ZERO_ONLY_PAYLOAD, DARK_PAYLOAD,
    DASH, START, MAGIC,
)
from .outgauge import open_socket, parse_rpm
from .wheel import (
    open_wheel, send_mode_init, send_telemetry_pct,
    send_no_data, send_zero_only, send_single_led, send_dark,
    startup_blink,
)
from .cli import main

__all__ = [
    "__version__",
    # protocol
    "frame", "indicator_mode_frame", "rpm_mode_frame", "telemetry_frame",
    "build_bitmask", "single_led_mask",
    "NO_DATA_PAYLOAD", "ZERO_ONLY_PAYLOAD", "DARK_PAYLOAD",
    "DASH", "START", "MAGIC",
    # outgauge
    "open_socket", "parse_rpm",
    # wheel
    "open_wheel", "send_mode_init", "send_telemetry_pct",
    "send_no_data", "send_zero_only", "send_single_led", "send_dark",
    "startup_blink",
    # cli
    "main",
]
