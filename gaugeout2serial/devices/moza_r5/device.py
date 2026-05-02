"""Moza R5 wheel dash — implements Device by writing serial frames over USB."""
from __future__ import annotations

import glob
import time
from typing import List, Optional

from serial import Serial

from . import protocol
from ..base import Device
from ...telemetry import TelemetrySample


DEFAULT_BAUD = 115200
DEVPATH_GLOB = "/dev/serial/by-id/usb-Gudsen_MOZA_R5_Base_*"

# Visual self-test on open()
STARTUP_DURATION_S = 2.0
STARTUP_SWEEPS = 2

# Pause between the two mode-set frames in init/heartbeat — boxflat does
# the same. The wheel firmware drops the second frame if it lands too soon.
MODE_SET_GAP_S = 0.05


class MozaR5(Device):
    name = "Moza R5"

    def __init__(self, devpath: str, baud: int = DEFAULT_BAUD):
        self.devpath = devpath
        self.baud = baud
        self._serial: Optional[Serial] = None
        self._last_pct: int = -1

    def open(self) -> None:
        if self._serial is not None:
            return
        self._serial = Serial(self.devpath, baudrate=self.baud,
                              exclusive=False, timeout=0.5)
        self._send_mode_init()

    def close(self) -> None:
        if self._serial is None:
            return
        try:
            self._send(protocol.telemetry_frame(protocol.DARK_PAYLOAD))
        finally:
            self._serial.close()
            self._serial = None

    def startup_indicator(self) -> None:
        sequence = list(range(1, 11)) + list(range(9, 0, -1))
        step_delay = (STARTUP_DURATION_S / STARTUP_SWEEPS) / len(sequence)
        for _ in range(STARTUP_SWEEPS):
            for n in sequence:
                self._send(protocol.telemetry_frame(protocol.single_led_mask(n)))
                time.sleep(step_delay)
        self._send(protocol.telemetry_frame(protocol.DARK_PAYLOAD))
        self._last_pct = -1

    def show_no_data(self) -> None:
        self._send(protocol.telemetry_frame(protocol.NO_DATA_PAYLOAD))
        self._last_pct = -1

    def show_idle(self) -> None:
        self._send(protocol.telemetry_frame(protocol.ZERO_ONLY_PAYLOAD))
        self._last_pct = -1

    def show_telemetry(self, sample: TelemetrySample, full_scale_rpm: float) -> None:
        rpm = sample.rpm or 0.0
        if full_scale_rpm <= 0:
            pct = 0
        else:
            pct = max(0, min(100, int(round(rpm / full_scale_rpm * 100))))
        if pct != self._last_pct:
            self._send(protocol.telemetry_frame(protocol.build_bitmask(pct)))
            self._last_pct = pct

    def heartbeat(self) -> None:
        if self._serial is None:
            return
        self._send_mode_init()

    @classmethod
    def discover(cls) -> List["MozaR5"]:
        return [cls(p) for p in sorted(glob.glob(DEVPATH_GLOB))]

    def _send_mode_init(self) -> None:
        self._send(protocol.indicator_mode_frame(1))  # 1 = RPM
        time.sleep(MODE_SET_GAP_S)
        self._send(protocol.rpm_mode_frame(0))        # 0 = Percent
        time.sleep(MODE_SET_GAP_S)

    def _send(self, frame: bytes) -> None:
        assert self._serial is not None, f"{self.name} not opened"
        self._serial.write(frame)
