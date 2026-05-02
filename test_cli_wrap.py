"""End-to-end test for the wrap-a-game CLI mode.

Uses a fake bridge (no real serial / UDP) and `/bin/true` as the
"game" so we exercise the subprocess + watcher + stop_event plumbing
without touching hardware.
"""
import shutil
import threading
import time
import unittest

from gaugeout2serial.bridge import Bridge
from gaugeout2serial.cli import _run_with_command, _strip_separator


class FakeSource:
    name = "fake"
    def open(self): pass
    def close(self): pass
    def poll(self, timeout: float):
        time.sleep(min(timeout, 0.05))
        return None


class FakeDevice:
    name = "fake"
    def __init__(self):
        self.opened = False
        self.closed = False

    def open(self): self.opened = True
    def close(self): self.closed = True
    def startup_indicator(self): pass
    def show_no_data(self): pass
    def show_idle(self): pass
    def show_telemetry(self, *a, **kw): pass
    def heartbeat(self): pass


class StripSeparatorTests(unittest.TestCase):
    def test_drops_leading_double_dash(self):
        self.assertEqual(_strip_separator(["--", "/bin/true"]), ["/bin/true"])

    def test_passthrough_without_separator(self):
        self.assertEqual(_strip_separator(["/bin/true", "-x"]),
                         ["/bin/true", "-x"])

    def test_empty(self):
        self.assertEqual(_strip_separator([]), [])


@unittest.skipIf(shutil.which("true") is None, "needs /bin/true")
class RunWithCommandTests(unittest.TestCase):
    def test_bridge_exits_when_child_exits(self):
        source = FakeSource()
        device = FakeDevice()
        bridge = Bridge(source, [device])

        # /bin/true returns 0 immediately. The watcher thread should set
        # bridge.stop_event, the bridge.run() loop should exit, and we
        # should propagate the exit code.
        rc = _run_with_command(bridge, ["true"])

        self.assertEqual(rc, 0)
        self.assertTrue(device.opened)
        self.assertTrue(device.closed)

    def test_propagates_nonzero_exit_code(self):
        source = FakeSource()
        device = FakeDevice()
        bridge = Bridge(source, [device])

        rc = _run_with_command(bridge, ["false"])
        self.assertNotEqual(rc, 0)

    def test_stop_terminates_run_promptly(self):
        # Independent test of stop() unblocking a running bridge from
        # another thread — same plumbing the wrap-mode watcher uses.
        source = FakeSource()
        device = FakeDevice()
        bridge = Bridge(source, [device])

        def _run():
            bridge.run()

        t = threading.Thread(target=_run)
        start = time.monotonic()
        t.start()
        time.sleep(0.1)  # let it spin up
        bridge.stop()
        t.join(timeout=3.0)
        elapsed = time.monotonic() - start

        self.assertFalse(t.is_alive(), "bridge.run() did not honour stop()")
        self.assertLess(elapsed, 3.0)


if __name__ == "__main__":
    unittest.main()
