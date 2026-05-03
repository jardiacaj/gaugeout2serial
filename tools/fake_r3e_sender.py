#!/usr/bin/env python3
"""
Send synthetic R3E UDP packets to gaugeout2serial.

Used to validate the Linux-side decode + bridge + wheel pipeline without
needing RaceRoom, Wine, or a real shmem→UDP relay. Builds packets at the
canonical r3e_shared offsets (the same ones the production decoder reads)
and sends them at ~30 Hz.

Modes:
    ramp        sweep 0..8000..0 RPM continuously (default)
    fixed       hold a specific RPM (--rpm)
    idle        emit zero-RPM packets (engine off)
    paused      emit zero-RPM with game_paused=1
    silent      emit nothing (timeout test — pair with --duration)
"""
from __future__ import annotations

import argparse
import math
import os
import socket
import struct
import sys
import time

# Allow `python3 tools/fake_r3e_sender.py` from the repo root without
# `pip install -e .` first.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gaugeout2serial.sources.r3e import (
    R3E_MIN_PACKET_SIZE,
    OFF_VERSION_MAJOR, OFF_VERSION_MINOR,
    OFF_GAME_PAUSED, OFF_GAME_IN_MENUS, OFF_GAME_IN_REPLAY,
    OFF_CAR_SPEED, OFF_ENGINE_RPS, OFF_MAX_ENGINE_RPS, OFF_UPSHIFT_RPS,
    OFF_GEAR, OFF_NUM_GEARS,
    OFF_THROTTLE, OFF_BRAKE, OFF_CLUTCH,
    OFF_FUEL_LEFT, OFF_FUEL_CAPACITY,
    OFF_ENGINE_TEMP, OFF_ENGINE_OIL_TEMP, OFF_ENGINE_OIL_PRESSURE,
)


SEND_HZ = 30


def _rpm_to_rps(rpm: float) -> float:
    return rpm * 2.0 * math.pi / 60.0


def make_packet(rpm: float, *, max_rpm: float = 8500.0, upshift: float = 8200.0,
                gear: int = 3, throttle: float = 0.5,
                paused: bool = False, in_menus: bool = False) -> bytes:
    buf = bytearray(R3E_MIN_PACKET_SIZE)
    struct.pack_into("<i", buf, OFF_VERSION_MAJOR, 2)
    struct.pack_into("<i", buf, OFF_VERSION_MINOR, 11)
    struct.pack_into("<i", buf, OFF_GAME_PAUSED, int(paused))
    struct.pack_into("<i", buf, OFF_GAME_IN_MENUS, int(in_menus))
    struct.pack_into("<i", buf, OFF_GAME_IN_REPLAY, 0)
    struct.pack_into("<f", buf, OFF_CAR_SPEED, 50.0)
    struct.pack_into("<f", buf, OFF_ENGINE_RPS, _rpm_to_rps(rpm))
    struct.pack_into("<f", buf, OFF_MAX_ENGINE_RPS, _rpm_to_rps(max_rpm))
    struct.pack_into("<f", buf, OFF_UPSHIFT_RPS, _rpm_to_rps(upshift))
    struct.pack_into("<i", buf, OFF_GEAR, gear)
    struct.pack_into("<i", buf, OFF_NUM_GEARS, 6)
    struct.pack_into("<f", buf, OFF_FUEL_LEFT, 30.0)
    struct.pack_into("<f", buf, OFF_FUEL_CAPACITY, 60.0)
    struct.pack_into("<f", buf, OFF_ENGINE_TEMP, 95.0)
    struct.pack_into("<f", buf, OFF_ENGINE_OIL_TEMP, 105.0)
    struct.pack_into("<f", buf, OFF_ENGINE_OIL_PRESSURE, 4.5)
    struct.pack_into("<f", buf, OFF_THROTTLE, throttle)
    struct.pack_into("<f", buf, OFF_BRAKE, 0.0)
    struct.pack_into("<f", buf, OFF_CLUTCH, 0.0)
    return bytes(buf)


def _ramp_iter():
    while True:
        for rpm in list(range(0, 8001, 50)) + list(range(8000, -1, -50)):
            yield rpm


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6000)
    ap.add_argument("--mode", choices=("ramp", "fixed", "idle", "paused", "silent"),
                    default="ramp")
    ap.add_argument("--rpm", type=float, default=4000.0,
                    help="RPM for --mode fixed (default 4000)")
    ap.add_argument("--duration", type=float, default=0.0,
                    help="seconds to send for; 0 = forever")
    ap.add_argument("--max-rpm", type=float, default=8500.0)
    ap.add_argument("--upshift-rpm", type=float, default=8200.0)
    args = ap.parse_args(argv)

    if args.mode == "silent":
        print(f"silent mode — not sending. Run for {args.duration or 'forever'}s.")
        try:
            time.sleep(args.duration if args.duration > 0 else 1e9)
        except KeyboardInterrupt:
            pass
        return 0

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (args.host, args.port)
    interval = 1.0 / SEND_HZ
    print(f"sending fake R3E packets to {args.host}:{args.port} "
          f"({SEND_HZ} Hz, mode={args.mode}). Ctrl-C to stop.")

    start = time.monotonic()
    sent = 0
    last_status = start

    def _maybe_status(now: float) -> None:
        nonlocal last_status
        if now - last_status >= 1.0:
            print(f"  sent {sent} packets ({sent / (now - start):.1f} Hz avg)")
            last_status = now

    def _should_continue() -> bool:
        if args.duration <= 0:
            return True
        return time.monotonic() - start < args.duration

    try:
        if args.mode == "ramp":
            for rpm in _ramp_iter():
                if not _should_continue():
                    break
                sock.sendto(make_packet(rpm, max_rpm=args.max_rpm,
                                        upshift=args.upshift_rpm), target)
                sent += 1
                _maybe_status(time.monotonic())
                time.sleep(interval)
        elif args.mode == "fixed":
            while _should_continue():
                sock.sendto(make_packet(args.rpm, max_rpm=args.max_rpm,
                                        upshift=args.upshift_rpm), target)
                sent += 1
                _maybe_status(time.monotonic())
                time.sleep(interval)
        elif args.mode == "idle":
            while _should_continue():
                sock.sendto(make_packet(0.0, max_rpm=args.max_rpm,
                                        upshift=args.upshift_rpm,
                                        gear=0, throttle=0.0), target)
                sent += 1
                _maybe_status(time.monotonic())
                time.sleep(interval)
        elif args.mode == "paused":
            while _should_continue():
                sock.sendto(make_packet(0.0, max_rpm=args.max_rpm,
                                        upshift=args.upshift_rpm,
                                        gear=0, throttle=0.0,
                                        paused=True), target)
                sent += 1
                _maybe_status(time.monotonic())
                time.sleep(interval)
    except KeyboardInterrupt:
        pass

    print(f"\ntotal sent: {sent} packets in {time.monotonic() - start:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
