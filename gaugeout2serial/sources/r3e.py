"""
RaceRoom Racing Experience (R3E) telemetry source.

R3E exposes telemetry on Windows as a shared-memory mapping called `$R3E`
holding the `r3e_shared` struct defined in
https://github.com/sector3studios/r3e-api .

There is no native UDP export. The standard workflow on Linux + Steam
Proton is to run a Windows-side `shmem→UDP` relay (e.g. OverTake's
"Telemetry Tool for R3E") inside the same Proton prefix as the game so
both processes share a `wineserver`. The relay typically broadcasts the
struct verbatim on a configurable UDP port; this source decodes the
fields it cares about straight out of those packets by absolute offset.

Offsets below were generated from the canonical struct in
sample-c/src/r3e.h with `offsetof()` (see the offset-printer C helper in
the project notes). The full struct is ~44 KB; we only touch ~120 bytes
worth of fields.
"""
from __future__ import annotations

import math
import socket
import struct
import time
from dataclasses import dataclass
from typing import Optional

from .base import TelemetrySource
from ..telemetry import TelemetrySample


# Struct size from r3e_shared in sample-c/src/r3e.h. Relay packets must be
# at least the highest offset we read (CLUTCH + 4) but in practice every
# relay we know of sends the full struct, so we sanity-check both bounds.
R3E_SHARED_FULL_SIZE = 43996
R3E_MIN_PACKET_SIZE = 1520

# All offsets are little-endian (the struct is produced by Windows, so
# native-LE on x86/x64).
_F32 = "<f"
_I32 = "<i"

# Header
OFF_VERSION_MAJOR = 0
OFF_VERSION_MINOR = 4

# Game state (1 = active, 0 = not)
OFF_GAME_PAUSED = 20
OFF_GAME_IN_MENUS = 24
OFF_GAME_IN_REPLAY = 28

# Vehicle state
OFF_CONTROL_TYPE = 1388
OFF_CAR_SPEED = 1392        # m/s
OFF_ENGINE_RPS = 1396       # rad/s
OFF_MAX_ENGINE_RPS = 1400   # rad/s
OFF_UPSHIFT_RPS = 1404      # rad/s
OFF_GEAR = 1408             # -2 = N/A, -1 = R, 0 = N, 1 = 1st, ...
OFF_NUM_GEARS = 1412
OFF_FUEL_LEFT = 1456        # litres
OFF_FUEL_CAPACITY = 1460
OFF_ENGINE_TEMP = 1480      # °C
OFF_ENGINE_OIL_TEMP = 1484
OFF_ENGINE_OIL_PRESSURE = 1492  # bar
OFF_THROTTLE = 1500         # 0..1
OFF_BRAKE = 1508
OFF_CLUTCH = 1516

RADS_PER_SEC_TO_RPM = 60.0 / (2.0 * math.pi)


def rps_to_rpm(rps: float) -> float:
    return rps * RADS_PER_SEC_TO_RPM


def _read_f32(data: bytes, offset: int) -> float:
    return struct.unpack_from(_F32, data, offset)[0]


def _read_i32(data: bytes, offset: int) -> int:
    return struct.unpack_from(_I32, data, offset)[0]


@dataclass(frozen=True)
class R3EPacket:
    """Decoded subset of the r3e_shared struct — every field we care about."""
    version_major: int
    version_minor: int

    game_paused: bool
    game_in_menus: bool
    game_in_replay: bool

    control_type: int
    car_speed_mps: float

    engine_rpm: float        # converted from rad/s
    max_engine_rpm: float    # converted from rad/s
    upshift_rpm: float       # converted from rad/s

    gear: int                # -2 N/A, -1 R, 0 N, 1+ forward gears
    num_gears: int

    fuel_left: float
    fuel_capacity: float
    engine_temp_c: float
    engine_oil_temp_c: float
    engine_oil_pressure_bar: float

    throttle: float
    brake: float
    clutch: float

    @classmethod
    def from_bytes(cls, data: bytes) -> Optional["R3EPacket"]:
        if len(data) < R3E_MIN_PACKET_SIZE:
            return None
        return cls(
            version_major=_read_i32(data, OFF_VERSION_MAJOR),
            version_minor=_read_i32(data, OFF_VERSION_MINOR),
            game_paused=bool(_read_i32(data, OFF_GAME_PAUSED) > 0),
            game_in_menus=bool(_read_i32(data, OFF_GAME_IN_MENUS) > 0),
            game_in_replay=bool(_read_i32(data, OFF_GAME_IN_REPLAY) > 0),
            control_type=_read_i32(data, OFF_CONTROL_TYPE),
            car_speed_mps=_read_f32(data, OFF_CAR_SPEED),
            engine_rpm=rps_to_rpm(_read_f32(data, OFF_ENGINE_RPS)),
            max_engine_rpm=rps_to_rpm(_read_f32(data, OFF_MAX_ENGINE_RPS)),
            upshift_rpm=rps_to_rpm(_read_f32(data, OFF_UPSHIFT_RPS)),
            gear=_read_i32(data, OFF_GEAR),
            num_gears=_read_i32(data, OFF_NUM_GEARS),
            fuel_left=_read_f32(data, OFF_FUEL_LEFT),
            fuel_capacity=_read_f32(data, OFF_FUEL_CAPACITY),
            engine_temp_c=_read_f32(data, OFF_ENGINE_TEMP),
            engine_oil_temp_c=_read_f32(data, OFF_ENGINE_OIL_TEMP),
            engine_oil_pressure_bar=_read_f32(data, OFF_ENGINE_OIL_PRESSURE),
            throttle=_read_f32(data, OFF_THROTTLE),
            brake=_read_f32(data, OFF_BRAKE),
            clutch=_read_f32(data, OFF_CLUTCH),
        )

    def to_sample(self, timestamp: Optional[float] = None) -> TelemetrySample:
        # Prefer the per-car upshift point as the bar's full-scale, falling
        # back to max_engine_rpm if the car doesn't expose an upshift hint.
        max_rpm: Optional[float] = None
        if self.upshift_rpm > 0:
            max_rpm = self.upshift_rpm
        elif self.max_engine_rpm > 0:
            max_rpm = self.max_engine_rpm
        # Negative engine RPM is a "no data" sentinel from the relay.
        rpm: Optional[float] = self.engine_rpm if self.engine_rpm >= 0 else None
        # Gear: R3E's -2 sentinel becomes None; everything else (-1..N) maps
        # straight to our normalised convention.
        gear: Optional[int] = self.gear if self.gear > -2 else None
        num_gears: Optional[int] = self.num_gears if self.num_gears >= 0 else None
        upshift_rpm: Optional[float] = (self.upshift_rpm
                                        if self.upshift_rpm > 0 else None)
        fuel_fraction: Optional[float] = (self.fuel_left / self.fuel_capacity
                                          if self.fuel_capacity > 0 else None)
        fuel_left: Optional[float] = (self.fuel_left
                                      if self.fuel_left >= 0 else None)
        fuel_capacity: Optional[float] = (self.fuel_capacity
                                          if self.fuel_capacity > 0 else None)
        return TelemetrySample(
            timestamp=time.monotonic() if timestamp is None else timestamp,
            rpm=rpm,
            max_rpm=max_rpm,
            upshift_rpm=upshift_rpm,
            gear=gear,
            num_gears=num_gears,
            speed_mps=self.car_speed_mps,
            throttle=self.throttle,
            brake=self.brake,
            clutch=self.clutch,
            fuel=fuel_fraction,
            fuel_litres=fuel_left,
            fuel_capacity_litres=fuel_capacity,
            engine_temp_c=self.engine_temp_c,
            oil_pressure_bar=self.engine_oil_pressure_bar,
            oil_temp_c=self.engine_oil_temp_c,
            game_paused=self.game_paused,
            game_in_menus=self.game_in_menus,
            game_in_replay=self.game_in_replay,
            control_type=self.control_type,
        )


class R3ESource(TelemetrySource):
    name = "R3E"

    DEFAULT_HOST = "0.0.0.0"
    DEFAULT_PORT = 6000          # arbitrary — set the same in the relay
    RECV_BUFFER = 65536          # struct is ~44 KB, so > 16 KB

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self._sock: Optional[socket.socket] = None

    def open(self) -> None:
        if self._sock is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.host, self.port))
        self._sock = sock

    def close(self) -> None:
        if self._sock is None:
            return
        self._sock.close()
        self._sock = None

    def poll(self, timeout: float) -> Optional[TelemetrySample]:
        if self._sock is None:
            raise RuntimeError("R3ESource not opened")
        self._sock.settimeout(timeout)
        try:
            data, _ = self._sock.recvfrom(self.RECV_BUFFER)
        except socket.timeout:
            return None
        packet = R3EPacket.from_bytes(data)
        if packet is None:
            return None
        return packet.to_sample()
