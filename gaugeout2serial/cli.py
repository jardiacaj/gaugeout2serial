"""CLI entry point: pick a source, autodiscover devices, run the bridge."""
from __future__ import annotations

import argparse
import sys
from typing import List

from .bridge import Bridge
from .devices.base import Device
from .devices.discovery import auto_discover_devices, all_device_classes
from .devices.moza_r5.device import DEFAULT_BAUD_RATE as MOZA_R5_BAUD_RATE, MozaR5
from .sources.outgauge import OutGaugeSource


def _parse_args(argv) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="gaugeout2serial",
        description="OutGauge UDP telemetry → serial-attached racing-wheel dashes",
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
    return ap.parse_args(argv)


def _resolve_devices(args: argparse.Namespace) -> List[Device]:
    """Return devices to drive. Explicit CLI overrides take precedence over
    autodiscovery; if both kinds are present we use only the explicit ones."""
    if args.moza_r5_devpath:
        return [MozaR5(args.moza_r5_devpath, baud_rate=args.moza_r5_baud)]
    return auto_discover_devices(all_device_classes())


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
    Bridge(source=source, devices=devices, verbose=args.verbose).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
