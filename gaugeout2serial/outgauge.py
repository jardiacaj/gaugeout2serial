"""
OutGauge UDP receiver.

OutGauge is the LFS-defined telemetry packet that BeamNG (and several other
sims) emits over UDP. The packet is 92 bytes, or 96 with the optional trailing
ID field. We only consume RPM (a little-endian f32 at offset 16); the full
field layout is documented inline below for reference.

    offset  type      field
      0     u32       time_ms
      4     char[4]   car
      8     u16       flags
     10     u8        gear         (0=R, 1=N, 2=1st, ...)
     11     u8        player_id
     12     f32       speed        (m/s)
     16     f32       rpm          ← we use this
     20     f32       turbo        (bar)
     24     f32       engine_temp  (°C)
     28     f32       fuel         (0..1)
     32     f32       oil_pressure (bar)
     36     f32       oil_temp     (°C)
     40     u32       dash_lights  (available bitmask)
     44     u32       show_lights  (active bitmask)
     48     f32       throttle     (0..1)
     52     f32       brake        (0..1)
     56     f32       clutch       (0..1)
     60     char[16]  display1
     76     char[16]  display2
     92     i32       id           (only if OutGaugeID set)
"""
from __future__ import annotations

import socket
import struct
from typing import Optional


VALID_LENGTHS = (92, 96)
RPM_OFFSET = 16


def open_socket(host: str, port: int, timeout_seconds: float) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    sock.settimeout(timeout_seconds)
    return sock


def parse_rpm(data: bytes) -> Optional[float]:
    """Return the RPM from an OutGauge packet, or None if the packet is the
    wrong size."""
    if len(data) not in VALID_LENGTHS:
        return None
    (rpm,) = struct.unpack_from("<f", data, RPM_OFFSET)
    return rpm
