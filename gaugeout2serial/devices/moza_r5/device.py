"""Moza R5 wheel dash — implements Device by writing serial frames over USB."""
from __future__ import annotations

import glob
import time
from typing import List, Optional

from serial import Serial

from . import protocol
from ..base import Device
from ...telemetry import TelemetrySample


DEFAULT_BAUD_RATE = 115200
DEVPATH_GLOB = "/dev/serial/by-id/usb-Gudsen_MOZA_R5_Base_*"

# Visual self-test on open()
STARTUP_INDICATOR_DURATION_SECONDS = 2.0
STARTUP_INDICATOR_SWEEP_COUNT = 2

# Pause between the two mode-set frames in init/heartbeat — boxflat does
# the same. The wheel firmware drops the second frame if it lands too soon.
MODE_SET_GAP_SECONDS = 0.05


class MozaR5(Device):
    name = "Moza R5"

    def __init__(self, devpath: str, baud_rate: int = DEFAULT_BAUD_RATE):
        self.devpath = devpath
        self.baud_rate = baud_rate
        self._serial_port: Optional[Serial] = None
        self._last_pct_sent: int = -1

    def open(self) -> None:
        if self._serial_port is not None:
            return
        self._serial_port = Serial(
            self.devpath, baudrate=self.baud_rate,
            exclusive=False, timeout=0.5,
        )
        self._send_mode_init()

    def close(self) -> None:
        if self._serial_port is None:
            return
        try:
            self._write_frame(protocol.telemetry_frame(protocol.DARK_PAYLOAD))
        finally:
            self._serial_port.close()
            self._serial_port = None

    def startup_indicator(self) -> None:
        led_sequence = list(range(1, 11)) + list(range(9, 0, -1))
        per_sweep_seconds = STARTUP_INDICATOR_DURATION_SECONDS / STARTUP_INDICATOR_SWEEP_COUNT
        step_delay_seconds = per_sweep_seconds / len(led_sequence)
        for _ in range(STARTUP_INDICATOR_SWEEP_COUNT):
            for led_index in led_sequence:
                self._write_frame(protocol.telemetry_frame(
                    protocol.single_led_mask(led_index)))
                time.sleep(step_delay_seconds)
        self._write_frame(protocol.telemetry_frame(protocol.DARK_PAYLOAD))
        self._last_pct_sent = -1

    def show_no_data(self) -> None:
        self._write_frame(protocol.telemetry_frame(protocol.NO_DATA_PAYLOAD))
        self._last_pct_sent = -1

    def show_idle(self) -> None:
        self._write_frame(protocol.telemetry_frame(protocol.ZERO_ONLY_PAYLOAD))
        self._last_pct_sent = -1

    def show_telemetry(self, sample: TelemetrySample, full_scale_rpm: float) -> None:
        rpm = sample.rpm or 0.0
        if full_scale_rpm <= 0:
            pct = 0
        else:
            pct = max(0, min(100, int(round(rpm / full_scale_rpm * 100))))
        if pct != self._last_pct_sent:
            self._write_frame(protocol.telemetry_frame(protocol.build_bitmask(pct)))
            self._last_pct_sent = pct

    def heartbeat(self) -> None:
        if self._serial_port is None:
            return
        self._send_mode_init()

    @classmethod
    def discover(cls) -> List["MozaR5"]:
        return [cls(devpath) for devpath in sorted(glob.glob(DEVPATH_GLOB))]

    def _send_mode_init(self) -> None:
        self._write_frame(protocol.indicator_mode_frame(1))  # 1 = RPM
        time.sleep(MODE_SET_GAP_SECONDS)
        self._write_frame(protocol.rpm_mode_frame(0))        # 0 = Percent
        time.sleep(MODE_SET_GAP_SECONDS)

    def _write_frame(self, frame_bytes: bytes) -> None:
        assert self._serial_port is not None, f"{self.name} not opened"
        self._serial_port.write(frame_bytes)
