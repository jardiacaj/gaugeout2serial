"""Tests for the bridge state machine — uses fake source/device."""
import unittest
from typing import List, Optional

from gaugeout2serial.bridge import (
    Bridge,
    NO_DATA_TIMEOUT_SECONDS,
    PEAK_RPM_RESET_TIMEOUT_SECONDS,
    REDLINE_FRACTION,
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
        self.fake_source = FakeSource()
        self.fake_device = FakeDevice()
        self.bridge = Bridge(self.fake_source, [self.fake_device])
        # Mimic Bridge.run() startup so _tick has fresh timestamps.
        self.bridge._last_packet_time = 0.0
        self.bridge._last_nonzero_rpm_time = 0.0
        self.bridge._last_heartbeat_time = 0.0

    def _last_state_event(self):
        for tag, *_ in reversed(self.fake_device.events):
            if tag in ("no_data", "idle", "telemetry"):
                return tag
        return None

    def test_telemetry_state_when_rpm_streaming(self):
        self.fake_source.queue.append(_sample(rpm=4000))
        self.bridge._tick(now=0.5)
        self.assertEqual(self._last_state_event(), "telemetry")
        self.assertGreater(self.bridge._peak_rpm, 0)

    def test_full_scale_uses_redline_fraction(self):
        self.fake_source.queue.append(_sample(rpm=8000))
        self.bridge._tick(now=0.5)
        # peak == 8000 → full_scale == 8000 * REDLINE_FRACTION
        last_telemetry_event = [e for e in self.fake_device.events
                                if e[0] == "telemetry"][-1]
        _, _, observed_full_scale = last_telemetry_event
        self.assertAlmostEqual(observed_full_scale, 8000 * REDLINE_FRACTION,
                               places=3)

    def test_no_data_state_after_silence(self):
        # First, get a real packet so last_packet_time advances.
        self.fake_source.queue.append(_sample(rpm=2000))
        self.bridge._tick(now=0.5)
        # Then poll with nothing in the queue and time well past the timeout.
        self.bridge._tick(now=0.5 + NO_DATA_TIMEOUT_SECONDS + 0.1)
        self.assertEqual(self._last_state_event(), "no_data")

    def test_idle_state_when_only_zero_rpm(self):
        # Stream zero-rpm packets; the nonzero-rpm streak grows past the timeout.
        self.fake_source.queue.append(_sample(rpm=0))
        self.bridge._tick(now=0.0)
        for next_time in (1.0, 2.0, 3.0, 4.0, 5.5):
            self.fake_source.queue.append(_sample(rpm=0))
            self.bridge._tick(now=next_time)
        self.assertEqual(self._last_state_event(), "idle")
        self.assertEqual(self.bridge._peak_rpm, 0.0)  # peak resets after IDLE

    def test_stop_event_breaks_run_loop(self):
        # Pre-fill the queue with samples so _tick has work each iteration.
        for _ in range(100):
            self.fake_source.queue.append(_sample(rpm=4000))
        self.bridge.stop()
        # run() should return immediately because the stop flag is set
        # before we even enter the while loop.
        self.bridge.run()
        # If we got here without hanging, the loop honoured the stop flag.

    def test_peak_resets_only_after_long_zero_streak(self):
        self.fake_source.queue.append(_sample(rpm=4000))
        self.bridge._tick(now=0.0)
        self.assertEqual(self.bridge._peak_rpm, 4000)
        # Brief zero gap (< timeout) — peak survives.
        self.fake_source.queue.append(_sample(rpm=0))
        self.bridge._tick(now=2.0)
        self.assertEqual(self.bridge._peak_rpm, 4000)
        # Long zero gap — peak resets.
        self.fake_source.queue.append(_sample(rpm=0))
        self.bridge._tick(now=2.0 + PEAK_RPM_RESET_TIMEOUT_SECONDS + 0.1)
        self.assertEqual(self.bridge._peak_rpm, 0.0)


if __name__ == "__main__":
    unittest.main()
