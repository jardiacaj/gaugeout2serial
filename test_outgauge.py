"""Tests for the OutGauge UDP packet parser."""
import struct
import unittest

from gaugeout2serial import outgauge


def _make_packet(rpm: float, with_id: bool = False) -> bytes:
    """Build a synthetic OutGauge packet with the given RPM."""
    base_size = 96 if with_id else 92
    buf = bytearray(base_size)
    struct.pack_into("<f", buf, outgauge.RPM_OFFSET, rpm)
    return bytes(buf)


class ParseRpmTests(unittest.TestCase):
    def test_parses_92_byte_packet(self):
        pkt = _make_packet(4321.0)
        self.assertAlmostEqual(outgauge.parse_rpm(pkt), 4321.0, places=2)

    def test_parses_96_byte_packet(self):
        pkt = _make_packet(8000.5, with_id=True)
        self.assertAlmostEqual(outgauge.parse_rpm(pkt), 8000.5, places=2)

    def test_zero_rpm(self):
        self.assertAlmostEqual(outgauge.parse_rpm(_make_packet(0.0)), 0.0)

    def test_rejects_unexpected_size(self):
        for size in (0, 32, 91, 93, 95, 97, 200):
            self.assertIsNone(outgauge.parse_rpm(b"\x00" * size), size)


if __name__ == "__main__":
    unittest.main()
