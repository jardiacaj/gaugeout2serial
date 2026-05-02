"""
Main loop. Owns the state machine that decides whether the source is
silent / idle / streaming live telemetry, and fans the resulting state
out to one or more devices.

The state determination is source/device-agnostic so future devices and
sources can plug in without re-implementing the timeout / autodiscovery
logic.
"""
from __future__ import annotations

import time
from typing import List, Optional

from .devices.base import Device, DeviceState
from .sources.base import TelemetrySource
from .telemetry import TelemetrySample


# Tunables — tweak with care, the wheel firmware standby behaviour depends
# on these. Bridge writes a frame to every device every iteration, so
# RECV_TIMEOUT also bounds the idle refresh rate.
RECV_TIMEOUT = 1.0
DARK_AFTER = 1.0
HEARTBEAT_PERIOD = 5.0
RESET_AFTER = 5.0
REDLINE_FRACTION = 0.95


class Bridge:
    def __init__(self, source: TelemetrySource, devices: List[Device],
                 verbose: bool = False):
        self.source = source
        self.devices = devices
        self.verbose = verbose

        self._peak_rpm = 0.0
        self._last_sample: Optional[TelemetrySample] = None
        self._last_packet = 0.0
        self._last_nonzero = 0.0
        self._last_heartbeat = 0.0
        self._last_log = 0.0
        self._prev_state: Optional[DeviceState] = None

    def run(self) -> None:
        self.source.open()
        for d in self.devices:
            d.open()
            d.startup_indicator()

        boot = time.monotonic()
        # Treat startup as "just got data" so the no-data indicator only
        # fires after DARK_AFTER seconds without a real packet.
        self._last_packet = boot
        self._last_nonzero = boot
        self._last_heartbeat = boot

        try:
            while True:
                self._tick(time.monotonic())
        except KeyboardInterrupt:
            print("\nshutting down")
        finally:
            for d in self.devices:
                try:
                    d.close()
                except Exception as e:
                    print(f"error closing {d.name}: {e}")
            self.source.close()

    def _tick(self, now: float) -> None:
        sample = self.source.poll(RECV_TIMEOUT)
        if sample is not None:
            self._last_sample = sample
            self._last_packet = now
            if sample.rpm is not None and sample.rpm > 0:
                self._last_nonzero = now
                if sample.rpm > self._peak_rpm:
                    self._peak_rpm = sample.rpm

        zero_streak = now - self._last_nonzero
        silent = now - self._last_packet

        if self._peak_rpm > 0 and zero_streak > RESET_AFTER:
            if self.verbose:
                print(f"no rpm for {RESET_AFTER:.0f}s -> resetting peak "
                      f"(was {self._peak_rpm:.0f})")
            self._peak_rpm = 0.0

        state = self._classify(silent, zero_streak)
        full_scale = self._peak_rpm * REDLINE_FRACTION if self._peak_rpm > 0 else 0.0

        for d in self.devices:
            if state == DeviceState.NO_DATA:
                d.show_no_data()
            elif state == DeviceState.IDLE:
                d.show_idle()
            elif self._last_sample is not None:
                d.show_telemetry(self._last_sample, full_scale)

        if state != self._prev_state:
            if self.verbose:
                self._log_state_transition(state)
            self._prev_state = state
        elif (state == DeviceState.TELEMETRY and self.verbose
              and now - self._last_log >= 1.0):
            self._log_telemetry(full_scale)
            self._last_log = now

        if now - self._last_heartbeat >= HEARTBEAT_PERIOD:
            for d in self.devices:
                d.heartbeat()
            self._last_heartbeat = now

    @staticmethod
    def _classify(silent: float, zero_streak: float) -> DeviceState:
        if silent > DARK_AFTER:
            return DeviceState.NO_DATA
        if zero_streak > RESET_AFTER:
            return DeviceState.IDLE
        return DeviceState.TELEMETRY

    def _log_state_transition(self, state: DeviceState) -> None:
        if state == DeviceState.NO_DATA:
            print(f"no packets >{DARK_AFTER:.0f}s -> NO_DATA")
        elif state == DeviceState.IDLE:
            print(f"only zero rpm for {RESET_AFTER:.0f}s -> IDLE")
        else:
            print(f"telemetry resumed (peak {self._peak_rpm:.0f})")

    def _log_telemetry(self, full_scale: float) -> None:
        s = self._last_sample
        if s is None or s.rpm is None:
            return
        pct = 0
        if full_scale > 0:
            pct = max(0, min(100, int(round(s.rpm / full_scale * 100))))
        print(f"rpm={s.rpm:6.0f}  pct={pct:3d}  peak={self._peak_rpm:.0f}")
