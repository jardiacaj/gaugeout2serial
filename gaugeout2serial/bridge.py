"""
Main loop. Owns the state machine that decides whether the source is
silent / idle / streaming live telemetry, and fans the resulting state
out to one or more devices.

The state determination is source/device-agnostic so future devices and
sources can plug in without re-implementing the timeout / autodiscovery
logic.
"""
from __future__ import annotations

import threading
import time
from typing import List, Optional

from .devices.base import Device, DeviceState
from .sources.base import TelemetrySource
from .telemetry import TelemetrySample


# Tunables — tweak with care, the wheel firmware standby behaviour depends
# on these. Bridge writes a frame to every device every iteration, so
# SOURCE_POLL_TIMEOUT also bounds the idle refresh rate.
SOURCE_POLL_TIMEOUT_SECONDS = 1.0
NO_DATA_TIMEOUT_SECONDS = 1.0
DEVICE_HEARTBEAT_INTERVAL_SECONDS = 5.0
PEAK_RPM_RESET_TIMEOUT_SECONDS = 5.0
TELEMETRY_LOG_INTERVAL_SECONDS = 1.0
REDLINE_FRACTION = 0.95


class Bridge:
    def __init__(self, source: TelemetrySource, devices: List[Device],
                 verbose: bool = False):
        self.source = source
        self.devices = devices
        self.verbose = verbose

        self._peak_rpm = 0.0
        self._last_sample: Optional[TelemetrySample] = None
        self._last_packet_time = 0.0
        self._last_nonzero_rpm_time = 0.0
        self._last_heartbeat_time = 0.0
        self._last_telemetry_log_time = 0.0
        self._previous_state: Optional[DeviceState] = None
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Signal the run() loop to exit at the next tick. Safe to call from
        another thread (used by the wrapped-command path when the child
        process exits)."""
        self._stop_event.set()

    def run(self) -> None:
        self.source.open()
        for device in self.devices:
            device.open()
            device.startup_indicator()

        start_time = time.monotonic()
        # Treat startup as "just got data" so the no-data indicator only
        # fires after NO_DATA_TIMEOUT_SECONDS without a real packet.
        self._last_packet_time = start_time
        self._last_nonzero_rpm_time = start_time
        self._last_heartbeat_time = start_time

        try:
            while not self._stop_event.is_set():
                self._tick(time.monotonic())
        except KeyboardInterrupt:
            print("\nshutting down")
        finally:
            for device in self.devices:
                try:
                    device.close()
                except Exception as exc:
                    print(f"error closing {device.name}: {exc}")
            self.source.close()

    def _tick(self, now: float) -> None:
        sample = self.source.poll(SOURCE_POLL_TIMEOUT_SECONDS)
        if sample is not None:
            self._last_sample = sample
            self._last_packet_time = now
            if sample.rpm is not None and sample.rpm > 0:
                self._last_nonzero_rpm_time = now
                if sample.rpm > self._peak_rpm:
                    self._peak_rpm = sample.rpm

        seconds_since_nonzero_rpm = now - self._last_nonzero_rpm_time
        seconds_since_packet = now - self._last_packet_time

        if (self._peak_rpm > 0
                and seconds_since_nonzero_rpm > PEAK_RPM_RESET_TIMEOUT_SECONDS):
            if self.verbose:
                print(f"no rpm for {PEAK_RPM_RESET_TIMEOUT_SECONDS:.0f}s -> "
                      f"resetting peak (was {self._peak_rpm:.0f})")
            self._peak_rpm = 0.0

        current_state = self._classify(seconds_since_packet, seconds_since_nonzero_rpm)
        full_scale_rpm = (self._peak_rpm * REDLINE_FRACTION
                          if self._peak_rpm > 0 else 0.0)

        for device in self.devices:
            if current_state == DeviceState.NO_DATA:
                device.show_no_data()
            elif current_state == DeviceState.IDLE:
                device.show_idle()
            elif self._last_sample is not None:
                device.show_telemetry(self._last_sample, full_scale_rpm)

        if current_state != self._previous_state:
            if self.verbose:
                self._log_state_transition(current_state)
            self._previous_state = current_state
        elif (current_state == DeviceState.TELEMETRY and self.verbose
              and now - self._last_telemetry_log_time >= TELEMETRY_LOG_INTERVAL_SECONDS):
            self._log_telemetry(full_scale_rpm)
            self._last_telemetry_log_time = now

        if now - self._last_heartbeat_time >= DEVICE_HEARTBEAT_INTERVAL_SECONDS:
            for device in self.devices:
                device.heartbeat()
            self._last_heartbeat_time = now

    @staticmethod
    def _classify(seconds_since_packet: float,
                  seconds_since_nonzero_rpm: float) -> DeviceState:
        if seconds_since_packet > NO_DATA_TIMEOUT_SECONDS:
            return DeviceState.NO_DATA
        if seconds_since_nonzero_rpm > PEAK_RPM_RESET_TIMEOUT_SECONDS:
            return DeviceState.IDLE
        return DeviceState.TELEMETRY

    def _log_state_transition(self, state: DeviceState) -> None:
        if state == DeviceState.NO_DATA:
            print(f"no packets >{NO_DATA_TIMEOUT_SECONDS:.0f}s -> NO_DATA")
        elif state == DeviceState.IDLE:
            print(f"only zero rpm for "
                  f"{PEAK_RPM_RESET_TIMEOUT_SECONDS:.0f}s -> IDLE")
        else:
            print(f"telemetry resumed (peak {self._peak_rpm:.0f})")

    def _log_telemetry(self, full_scale_rpm: float) -> None:
        sample = self._last_sample
        if sample is None or sample.rpm is None:
            return
        pct = 0
        if full_scale_rpm > 0:
            pct = max(0, min(100, int(round(sample.rpm / full_scale_rpm * 100))))
        print(f"rpm={sample.rpm:6.0f}  pct={pct:3d}  peak={self._peak_rpm:.0f}")
