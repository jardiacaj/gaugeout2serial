"""
Main loop: receive OutGauge UDP packets, drive the Moza dash LED bar.

State machine (priority high → low):
    NO_DATA     no UDP packet for >DARK_AFTER         → LEDs 5+6
    ZERO_ONLY   packets flowing but RPM == 0 for      → LEDs 4+7
                 RESET_AFTER seconds (engine off /
                 paused). Also resets the autodiscovered peak.
    TELEMETRY   active engine RPM                     → bar (75%-95% solid,
                                                          97% blink)

The wheel firmware reverts to a slow-flash standby state if it stops seeing
writes for a few seconds. Every loop iteration writes a frame for the current
state — at packet rate during telemetry, at the recv timeout (1 Hz) when idle.
"""
from __future__ import annotations

import argparse
import socket
import sys
import time

from . import protocol
from . import outgauge
from . import wheel
from .protocol import build_bitmask


DEFAULT_DEVPATH = (
    "/dev/serial/by-id/usb-Gudsen_MOZA_R5_Base_3B004F001951343132373635-if00"
)
DEFAULT_OUTGAUGE_HOST = "0.0.0.0"
DEFAULT_OUTGAUGE_PORT = 4444

RECV_TIMEOUT = 1.0          # also our minimum refresh rate for the wheel
DARK_AFTER = 1.0            # show no-data indicator after this much silence
HEARTBEAT_PERIOD = 5.0      # re-send mode-set frames every N seconds
RESET_AFTER = 5.0           # reset autodiscovered peak after this much idle/zero
REDLINE_FRACTION = 0.95     # full bar lights at this fraction of peak seen


def _parse_args(argv):
    ap = argparse.ArgumentParser(prog="gaugeout2serial",
                                 description=__doc__.strip().splitlines()[0])
    ap.add_argument("--devpath", default=DEFAULT_DEVPATH,
                    help="serial device path of the wheel "
                         f"(default {DEFAULT_DEVPATH})")
    ap.add_argument("--baud", type=int, default=wheel.DEFAULT_BAUD,
                    help=f"serial baud rate (default {wheel.DEFAULT_BAUD})")
    ap.add_argument("--host", default=DEFAULT_OUTGAUGE_HOST,
                    help=f"UDP host to bind for OutGauge (default {DEFAULT_OUTGAUGE_HOST})")
    ap.add_argument("--port", type=int, default=DEFAULT_OUTGAUGE_PORT,
                    help=f"OutGauge UDP port (default {DEFAULT_OUTGAUGE_PORT})")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="print rpm/pct/mask once per second + state transitions")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)

    sock = outgauge.open_socket(args.host, args.port, RECV_TIMEOUT)
    print(f"listening for OutGauge on {args.host}:{args.port}")

    s = wheel.open_wheel(args.devpath, args.baud)
    wheel.send_mode_init(s)
    wheel.startup_blink(s)
    print(f"wheel initialised on {args.devpath} @ {args.baud}")

    boot = time.monotonic()
    peak_rpm = 0.0
    last_packet = boot           # treat startup as "just got data" so the
                                 # no-data indicator only fires after DARK_AFTER
    last_nonzero = boot
    last_heartbeat = boot
    last_log = 0.0
    in_no_data_prev = False
    in_zero_only_prev = False
    last_pct = -1
    pct = 0
    rpm = 0.0

    try:
        while True:
            now = time.monotonic()

            try:
                data, _ = sock.recvfrom(256)
            except socket.timeout:
                data = None

            if data is not None:
                parsed = outgauge.parse_rpm(data)
                if parsed is None:
                    continue
                rpm = parsed
                last_packet = now
                if rpm > 0:
                    last_nonzero = now
                    if rpm > peak_rpm:
                        peak_rpm = rpm

            zero_streak = now - last_nonzero
            silent = now - last_packet

            if peak_rpm > 0 and zero_streak > RESET_AFTER:
                if args.verbose:
                    print(f"no rpm for {RESET_AFTER:.0f}s -> resetting peak "
                          f"(was {peak_rpm:.0f})")
                peak_rpm = 0.0

            in_no_data = silent > DARK_AFTER
            in_zero_only = (not in_no_data and zero_streak > RESET_AFTER)

            if in_no_data:
                wheel.send_no_data(s)
                last_pct = -1
                if not in_no_data_prev and args.verbose:
                    print(f"no packets >{DARK_AFTER:.0f}s -> LEDs 5+6")
            elif in_zero_only:
                wheel.send_zero_only(s)
                last_pct = -1
                if not in_zero_only_prev and args.verbose:
                    print(f"only zero rpm for {RESET_AFTER:.0f}s -> LEDs 4+7")
            else:
                if peak_rpm > 0:
                    full_scale = peak_rpm * REDLINE_FRACTION
                    pct = max(0, min(100, int(round(rpm / full_scale * 100))))
                else:
                    pct = 0
                if pct != last_pct:
                    wheel.send_telemetry_pct(s, pct)
                    last_pct = pct

                if args.verbose and now - last_log >= 1.0:
                    mask = build_bitmask(pct)
                    print(f"rpm={rpm:6.0f}  pct={pct:3d}  mask={mask.hex(' ')}"
                          f"  peak={peak_rpm:.0f}")
                    last_log = now

            in_no_data_prev = in_no_data
            in_zero_only_prev = in_zero_only

            if now - last_heartbeat >= HEARTBEAT_PERIOD:
                wheel.send_mode_init(s)
                last_heartbeat = now
    except KeyboardInterrupt:
        print("\nshutting down")
        wheel.send_dark(s)
        s.close()
        sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
