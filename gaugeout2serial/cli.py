"""CLI entry point: pick a source, autodiscover devices, run the bridge.

Two run modes:

* Standalone — `gaugeout2serial -v`. Bridge runs until Ctrl+C.
* Wrap-a-game — `gaugeout2serial -- /path/to/game [args...]`. Spawns the
  game as a child process, runs the bridge alongside it, and shuts the
  bridge down cleanly when the game exits. Drop-in compatible with Steam
  launch options (`gaugeout2serial -- %command%`) the same way mangohud
  and gamemoderun are.
"""
from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import threading
from typing import List

from .bridge import Bridge
from .devices.base import Device
from .devices.discovery import all_device_classes, auto_discover_devices
from .devices.moza_r5.device import DEFAULT_BAUD_RATE as MOZA_R5_BAUD_RATE, MozaR5
from .sources.outgauge import OutGaugeSource


CHILD_TERM_TIMEOUT_SECONDS = 5.0
WATCHER_JOIN_TIMEOUT_SECONDS = 2.0


def _parse_args(argv) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="gaugeout2serial",
        description="OutGauge UDP telemetry → serial-attached racing-wheel dashes",
        epilog="To wrap a game: `gaugeout2serial -- /path/to/game [args...]`. "
               "The bridge exits when the game exits.",
    )

    src = ap.add_argument_group("source (OutGauge UDP)")
    src.add_argument("--host", default=OutGaugeSource.DEFAULT_HOST,
                     help=f"UDP host to bind (default {OutGaugeSource.DEFAULT_HOST})")
    src.add_argument("--port", type=int, default=OutGaugeSource.DEFAULT_PORT,
                     help=f"UDP port (default {OutGaugeSource.DEFAULT_PORT})")

    dev = ap.add_argument_group("devices")
    dev.add_argument("--moza-r5-devpath", default=None,
                     help="explicit Moza R5 serial path "
                          "(default: auto-discover via /dev/serial/by-id/)")
    dev.add_argument("--moza-r5-baud", type=int, default=MOZA_R5_BAUD_RATE,
                     help=f"Moza R5 baud rate (default {MOZA_R5_BAUD_RATE})")
    dev.add_argument("--list-devices", action="store_true",
                     help="list auto-discovered devices and exit")

    ap.add_argument("-v", "--verbose", action="store_true",
                    help="print state transitions and per-second telemetry summaries")

    ap.add_argument("command", nargs=argparse.REMAINDER,
                    help="optional game command to run alongside the bridge "
                         "(use `--` to separate from gaugeout2serial flags)")
    return ap.parse_args(argv)


def _resolve_devices(args: argparse.Namespace) -> List[Device]:
    """Return devices to drive. Explicit CLI overrides take precedence over
    autodiscovery; if both kinds are present we use only the explicit ones."""
    if args.moza_r5_devpath:
        return [MozaR5(args.moza_r5_devpath, baud_rate=args.moza_r5_baud)]
    return auto_discover_devices(all_device_classes())


def _strip_separator(command: List[str]) -> List[str]:
    """argparse.REMAINDER preserves a leading `--`; drop it."""
    if command and command[0] == "--":
        return command[1:]
    return command


def main(argv=None) -> int:
    args = _parse_args(argv)

    if args.list_devices:
        found = auto_discover_devices(all_device_classes())
        if not found:
            print("no devices auto-discovered.")
            return 0
        for d in found:
            print(f"{d.name}: {getattr(d, 'devpath', '?')}")
        return 0

    devices = _resolve_devices(args)
    if not devices:
        print("no devices found. Pass --moza-r5-devpath PATH "
              "or check /dev/serial/by-id/", file=sys.stderr)
        return 1

    summary = ", ".join(f"{d.name} ({getattr(d, 'devpath', '?')})" for d in devices)
    print(f"devices: {summary}")
    print(f"listening for OutGauge on {args.host}:{args.port}")

    source = OutGaugeSource(host=args.host, port=args.port)
    bridge = Bridge(source=source, devices=devices, verbose=args.verbose)

    command = _strip_separator(args.command)
    if command:
        return _run_with_command(bridge, command)

    bridge.run()
    return 0


def _run_with_command(bridge: Bridge, command: List[str]) -> int:
    """Spawn `command` as a child process, run the bridge alongside it,
    and stop the bridge when the child exits. SIGINT/SIGTERM received by
    this process are forwarded to the child."""
    try:
        proc = subprocess.Popen(command)
    except FileNotFoundError as exc:
        print(f"failed to launch {command[0]}: {exc}", file=sys.stderr)
        return 127

    print(f"launched: {' '.join(command)} (pid {proc.pid})")

    child_exit_code: List[int] = [0]

    def _watch_child() -> None:
        child_exit_code[0] = proc.wait()
        bridge.stop()

    watcher_thread = threading.Thread(target=_watch_child, daemon=True)
    watcher_thread.start()

    def _forward_signal(signum, _frame) -> None:
        if proc.poll() is None:
            try:
                proc.send_signal(signum)
            except ProcessLookupError:
                pass

    previous_handlers = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[sig] = signal.signal(sig, _forward_signal)

    try:
        bridge.run()
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)

        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=CHILD_TERM_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill()
            except ProcessLookupError:
                pass

        watcher_thread.join(timeout=WATCHER_JOIN_TIMEOUT_SECONDS)

    return child_exit_code[0]


if __name__ == "__main__":
    sys.exit(main())
