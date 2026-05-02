"""
Moza serial framing primitives — pure functions, no I/O.

Frame layout (per boxflat data/serial.yml):
    start (0x7e) | length | write_group | device_id | id_bytes | payload | csum

    length  = len(payload) + len(id_bytes)
    csum    = (MAGIC + sum(prev bytes)) % 256

device-ids: main = 18 (0x12), base = 19 (0x13), dash = 20 (0x14).
boxflat's connection_manager.get_device_id() rewrites any non-base connected
device to main = 0x12 at send time, so all dash commands from this bridge use
0x12 even though the dash subsystem is logically 0x14.
"""
from __future__ import annotations

START = 0x7E
MAGIC = 13
DASH = 0x12

WRITE_GROUP_MODE = 0x32       # boxflat "write=50" — set a config field
WRITE_GROUP_TELEMETRY = 0x41  # boxflat "write=65" — push runtime telemetry

ID_INDICATOR_MODE = (17, 0)
ID_RPM_MODE = (13,)
ID_SEND_TELEMETRY = (253, 222)


def frame(write_group: int, device_id: int, id_bytes: bytes, payload: bytes) -> bytes:
    length = len(payload) + len(id_bytes)
    body = bytes([START, length, write_group, device_id]) + id_bytes + payload
    return body + bytes([(MAGIC + sum(body)) % 256])


def indicator_mode_frame(mode: int) -> bytes:
    """0=Off, 1=RPM, 2=On."""
    return frame(WRITE_GROUP_MODE, DASH, bytes(ID_INDICATOR_MODE), bytes([mode]))


def rpm_mode_frame(mode: int) -> bytes:
    """0=Percent (matches our bitmask payload), 1=raw RPM."""
    return frame(WRITE_GROUP_MODE, DASH, bytes(ID_RPM_MODE), bytes([mode]))


def telemetry_frame(payload4: bytes) -> bytes:
    if len(payload4) != 4:
        raise ValueError("telemetry payload must be 4 bytes")
    return frame(WRITE_GROUP_TELEMETRY, DASH, bytes(ID_SEND_TELEMETRY), payload4)


def build_bitmask(pct: int) -> bytes:
    """GT3-style shift bar: first LED at 75 %, last solid at 95 %, blink at 97 %.

    Returns the 4-byte telemetry payload. Bytes 0..1 stay zero; the wheel
    firmware reads the LED bitmask out of bytes 2 (b8) and 3 (b9).
    """
    b8 = 0
    b9 = 0
    thresholds_b9 = (75, 80, 83, 86, 88, 90, 92, 93)  # LEDs 1..8
    for i, t in enumerate(thresholds_b9):
        if pct >= t:
            b9 |= 1 << i
    if pct >= 94:
        b8 |= 1 << 0  # LED 9
    if pct >= 95:
        b8 |= 1 << 1  # LED 10
    if pct >= 97:
        b8 |= 1 << 7  # blinking bit
    return bytes([0x00, 0x00, b8, b9])


def single_led_mask(n: int) -> bytes:
    """n in 1..10. byte9 bits 0..7 hold LEDs 1..8; byte8 bits 0/1 hold 9/10."""
    if 1 <= n <= 8:
        return bytes([0x00, 0x00, 0x00, 1 << (n - 1)])
    if n == 9:
        return bytes([0x00, 0x00, 1 << 0, 0x00])
    if n == 10:
        return bytes([0x00, 0x00, 1 << 1, 0x00])
    return bytes([0x00, 0x00, 0x00, 0x00])


# Symmetric "no telemetry" indicators on a 10-LED row (no true centre):
NO_DATA_PAYLOAD = bytes([0x00, 0x00, 0x00, 0x30])    # LEDs 5+6 (centre)
ZERO_ONLY_PAYLOAD = bytes([0x00, 0x00, 0x02, 0x01])  # LEDs 1+10 (extremes)
DARK_PAYLOAD = bytes([0x00, 0x00, 0x00, 0x00])
