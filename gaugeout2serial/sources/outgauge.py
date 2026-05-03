"""
OutGauge UDP telemetry source.

OutGauge is the LFS-defined dashboard packet that BeamNG, LFS, and several
other sims emit. The packet is 92 bytes (or 96 with the optional trailing
ID field). Layout reproduced inline below for reference.

    offset  type      field
      0     u32       time_ms
      4     char[4]   car
      8     u16       flags
     10     u8        gear         (0=R, 1=N, 2=1st, ...)
     11     u8        player_id
     12     f32       speed_mps
     16     f32       rpm
     20     f32       turbo_bar
     24     f32       engine_temp_c
     28     f32       fuel         (0..1)
     32     f32       oil_pressure_bar
     36     f32       oil_temp_c
     40     u32       dash_lights  (available bitmask)
     44     u32       show_lights  (active bitmask)
     48     f32       throttle     (0..1)
     52     f32       brake        (0..1)
     56     f32       clutch       (0..1)
     60     char[16]  display1
     76     char[16]  display2
     92     i32       id           (only if 96 bytes)
"""
from __future__ import annotations

import socket
import struct
import time
from dataclasses import dataclass
from enum import IntFlag
from typing import Optional

from .base import TelemetrySource
from ..telemetry import TelemetrySample


class OutGaugeFlag(IntFlag):
    """Flags bitfield (u16 at packet offset 8). LFS-defined `OG_*` constants.

    The two key flags are SHIFT/CTRL (modifier keys held during the frame)
    and the unit/turbo-display preferences the sim wants the dash to honour.
    """
    SHIFT = 0x0001            # OG_SHIFT — shift key held
    CTRL = 0x0002             # OG_CTRL  — ctrl key held
    TURBO = 0x2000            # OG_TURBO — show the turbo gauge
    KM = 0x4000               # OG_KM    — user prefers km/h (else mph)
    BAR = 0x8000              # OG_BAR   — user prefers bar (else psi)


PACKET_FORMAT = "<I4sHBBfffffffIIfff16s16s"
PACKET_SIZE = 92         # struct.calcsize(PACKET_FORMAT)
PACKET_SIZE_WITH_ID = 96
ID_FORMAT = "<i"

assert struct.calcsize(PACKET_FORMAT) == PACKET_SIZE


def _zterm(b: bytes) -> str:
    """Decode a zero-terminated ASCII field."""
    z = b.find(b"\x00")
    if z >= 0:
        b = b[:z]
    return b.decode("ascii", errors="replace")


@dataclass(frozen=True)
class OutGaugePacket:
    """Decoded OutGauge wire packet — every field, in source units."""
    time_ms: int
    car: str
    flags: int
    gear: int
    player_id: int
    speed_mps: float
    rpm: float
    turbo_bar: float
    engine_temp_c: float
    fuel: float
    oil_pressure_bar: float
    oil_temp_c: float
    dash_lights: int
    show_lights: int
    throttle: float
    brake: float
    clutch: float
    display1: str
    display2: str
    id: Optional[int] = None

    @property
    def decoded_flags(self) -> OutGaugeFlag:
        """Return the flags field as an IntFlag mask of known bits.

        Bits outside the documented LFS set are masked out, so unrecognised
        future flags don't show up here; inspect `self.flags` for the raw
        wire value.
        """
        known = (OutGaugeFlag.SHIFT | OutGaugeFlag.CTRL | OutGaugeFlag.TURBO
                 | OutGaugeFlag.KM | OutGaugeFlag.BAR)
        return OutGaugeFlag(self.flags & int(known))

    @property
    def shift_held(self) -> bool:
        return bool(self.flags & OutGaugeFlag.SHIFT)

    @property
    def ctrl_held(self) -> bool:
        return bool(self.flags & OutGaugeFlag.CTRL)

    @property
    def show_turbo(self) -> bool:
        return bool(self.flags & OutGaugeFlag.TURBO)

    @property
    def prefers_km(self) -> bool:
        return bool(self.flags & OutGaugeFlag.KM)

    @property
    def prefers_bar(self) -> bool:
        return bool(self.flags & OutGaugeFlag.BAR)

    @classmethod
    def from_bytes(cls, data: bytes) -> Optional["OutGaugePacket"]:
        if len(data) not in (PACKET_SIZE, PACKET_SIZE_WITH_ID):
            return None
        (time_ms, car, flags, gear, player_id, speed_mps, rpm, turbo_bar,
         engine_temp_c, fuel, oil_pressure_bar, oil_temp_c,
         dash_lights, show_lights, throttle, brake, clutch,
         display1, display2) = struct.unpack(PACKET_FORMAT, data[:PACKET_SIZE])
        id_value: Optional[int] = None
        if len(data) == PACKET_SIZE_WITH_ID:
            (id_value,) = struct.unpack(ID_FORMAT, data[PACKET_SIZE:PACKET_SIZE_WITH_ID])
        return cls(
            time_ms=time_ms,
            car=_zterm(car),
            flags=flags,
            gear=gear,
            player_id=player_id,
            speed_mps=speed_mps,
            rpm=rpm,
            turbo_bar=turbo_bar,
            engine_temp_c=engine_temp_c,
            fuel=fuel,
            oil_pressure_bar=oil_pressure_bar,
            oil_temp_c=oil_temp_c,
            dash_lights=dash_lights,
            show_lights=show_lights,
            throttle=throttle,
            brake=brake,
            clutch=clutch,
            display1=_zterm(display1),
            display2=_zterm(display2),
            id=id_value,
        )

    def to_sample(self, timestamp: Optional[float] = None) -> TelemetrySample:
        # OutGauge encodes gear as 0=R, 1=N, 2=1st...; normalise by -1 so it
        # matches the package-wide convention (-1=R, 0=N, 1+ forward).
        return TelemetrySample(
            timestamp=time.monotonic() if timestamp is None else timestamp,
            rpm=self.rpm,
            speed_mps=self.speed_mps,
            gear=self.gear - 1,
            throttle=self.throttle,
            brake=self.brake,
            clutch=self.clutch,
            fuel=self.fuel,
            turbo_bar=self.turbo_bar,
            engine_temp_c=self.engine_temp_c,
            oil_pressure_bar=self.oil_pressure_bar,
            oil_temp_c=self.oil_temp_c,
            dash_lights=self.dash_lights,
            show_lights=self.show_lights,
            car=self.car,
            flags=self.flags,
            player_id=self.player_id,
            display1=self.display1,
            display2=self.display2,
            source_id=self.id,
        )


class OutGaugeSource(TelemetrySource):
    name = "OutGauge"

    DEFAULT_HOST = "0.0.0.0"
    DEFAULT_PORT = 4444
    RECV_BUFFER = 256

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
            raise RuntimeError("OutGaugeSource not opened")
        self._sock.settimeout(timeout)
        try:
            data, _ = self._sock.recvfrom(self.RECV_BUFFER)
        except socket.timeout:
            return None
        packet = OutGaugePacket.from_bytes(data)
        if packet is None:
            return None
        return packet.to_sample()
