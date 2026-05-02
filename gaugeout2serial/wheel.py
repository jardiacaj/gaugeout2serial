"""
Thin Serial wrapper that turns protocol frames into wheel writes.

All dash-side state changes go through one of these helpers so the framing
logic stays in protocol.py and this file stays trivially mockable.
"""
from __future__ import annotations

import time

from serial import Serial

from . import protocol


DEFAULT_BAUD = 115200


def open_wheel(devpath: str, baud: int = DEFAULT_BAUD) -> Serial:
    """Open the wheel serial port. exclusive=False so boxflat can co-exist on
    the read side while we're writing telemetry (boxflat must not be writing
    at the same time though)."""
    return Serial(devpath, baudrate=baud, exclusive=False, timeout=0.5)


def send_mode_init(s: Serial) -> None:
    s.write(protocol.indicator_mode_frame(1))  # 1 = RPM
    time.sleep(0.05)
    s.write(protocol.rpm_mode_frame(0))        # 0 = Percent
    time.sleep(0.05)


def send_telemetry_pct(s: Serial, pct: int) -> None:
    s.write(protocol.telemetry_frame(protocol.build_bitmask(pct)))


def send_no_data(s: Serial) -> None:
    s.write(protocol.telemetry_frame(protocol.NO_DATA_PAYLOAD))


def send_zero_only(s: Serial) -> None:
    s.write(protocol.telemetry_frame(protocol.ZERO_ONLY_PAYLOAD))


def send_single_led(s: Serial, n: int) -> None:
    s.write(protocol.telemetry_frame(protocol.single_led_mask(n)))


def send_dark(s: Serial) -> None:
    s.write(protocol.telemetry_frame(protocol.DARK_PAYLOAD))


def startup_blink(s: Serial, total_seconds: float = 2.0, sweeps: int = 2) -> None:
    """Single-LED sweep 1→10→1, repeated. Confirms the wheel-write path
    end-to-end before live telemetry starts arriving."""
    sequence = list(range(1, 11)) + list(range(9, 0, -1))  # 19 steps
    step_delay = (total_seconds / sweeps) / len(sequence)
    for _ in range(sweeps):
        for n in sequence:
            send_single_led(s, n)
            time.sleep(step_delay)
    send_dark(s)
