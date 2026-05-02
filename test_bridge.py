"""Tests for the bridge state machine — uses fake source/device."""
import unittest
from typing import List, Optional

from gaugeout2serial.bridge import (
    Bridge, DARK_AFTER, REDLINE_FRACTION, RESET_AFTER,
)
from gaugeout2serial.devices.base import Device, DeviceState
from gaugeout2serial.sources.base import TelemetrySource
from gaugeout2serial.telemetry import TelemetrySample


class FakeSource(TelemetrySource):
    name = "fake"

    def __init__(self):
        self.queue: List[Optional[TelemetrySample]] = []

    def open(self): pass
    def close(self): pass

    def poll(self, timeout: float):
        if not self.queue:
            return None
        return self.queue.pop(0)


class FakeDevice(Device):
    name = "fake"

    def __init__(self):
        self.events: List[tuple] = []

    def open(self): self.events.append(("open",))
    def close(self): self.events.append(("close",))
    def startup_indicator(self): self.events.append(("startup",))
    def show_no_data(self): self.events.append(("no_data",))
    def show_idle(self): self.events.append(("idle",))
    def show_telemetry(self, sample, full_scale_rpm):
        self.events.append(("telemetry", sample.rpm, full_scale_rpm))
    def heartbeat(self): self.events.append(("heartbeat",))


def _sample(rpm, ts=0.0):
    return TelemetrySample(timestamp=ts, rpm=rpm)


class BridgeStateTests(unittest.TestCase):
    def setUp(self):
        self.src = FakeSource()
        self.dev = FakeDevice()
        self.b = Bridge(self.src, [self.dev])
        # Mimic Bridge.run() startup so _tick has fresh timestamps.
        self.b._last_packet = 0.0
        self.b._last_nonzero = 0.0
        self.b._last_heartbeat = 0.0

    def _last_state_event(self):
        for tag, *rest in reversed(self.dev.events):
            if tag in ("no_data", "idle", "telemetry"):
                return tag
        return None

    def test_telemetry_state_when_rpm_streaming(self):
        self.src.queue.append(_sample(rpm=4000))
        self.b._tick(now=0.5)
        self.assertEqual(self._last_state_event(), "telemetry")
        self.assertGreater(self.b._peak_rpm, 0)

    def test_full_scale_uses_redline_fraction(self):
        self.src.queue.append(_sample(rpm=8000))
        self.b._tick(now=0.5)
        # peak == 8000 → full_scale == 8000 * REDLINE_FRACTION
        last_telem = [e for e in self.dev.events if e[0] == "telemetry"][-1]
        _, _, full_scale = last_telem
        self.assertAlmostEqual(full_scale, 8000 * REDLINE_FRACTION, places=3)

    def test_no_data_state_after_silence(self):
        # First, get a real packet so last_packet/last_nonzero advance to 0.5.
        self.src.queue.append(_sample(rpm=2000))
        self.b._tick(now=0.5)
        # Then poll with nothing in the queue and time well past DARK_AFTER.
        self.b._tick(now=0.5 + DARK_AFTER + 0.1)
        self.assertEqual(self._last_state_event(), "no_data")

    def test_idle_state_when_only_zero_rpm(self):
        # Stream zero-rpm packets; nonzero_streak grows past RESET_AFTER.
        self.src.queue.append(_sample(rpm=0))
        self.b._tick(now=0.0)
        # advance time but keep a fresh packet flowing each tick
        for t in (1.0, 2.0, 3.0, 4.0, 5.5):
            self.src.queue.append(_sample(rpm=0))
            self.b._tick(now=t)
        self.assertEqual(self._last_state_event(), "idle")
        self.assertEqual(self.b._peak_rpm, 0.0)  # peak resets after IDLE

    def test_peak_resets_only_after_long_zero_streak(self):
        self.src.queue.append(_sample(rpm=4000))
        self.b._tick(now=0.0)
        self.assertEqual(self.b._peak_rpm, 4000)
        # Brief zero gap (< RESET_AFTER) — peak survives.
        self.src.queue.append(_sample(rpm=0))
        self.b._tick(now=2.0)
        self.assertEqual(self.b._peak_rpm, 4000)
        # Long zero gap — peak resets.
        self.src.queue.append(_sample(rpm=0))
        self.b._tick(now=2.0 + RESET_AFTER + 0.1)
        self.assertEqual(self.b._peak_rpm, 0.0)


if __name__ == "__main__":
    unittest.main()
