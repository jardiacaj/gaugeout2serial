"""Tests for the OutGauge UDP packet decoder."""
import struct
import unittest

from gaugeout2serial.sources.outgauge import (
    OutGaugePacket, PACKET_FORMAT, PACKET_SIZE, PACKET_SIZE_WITH_ID,
)


def _make_packet(rpm=0.0, *, with_id=False, gear=1, throttle=0.0, brake=0.0,
                 car=b"GTR\x00", display1=b"", display2=b"") -> bytes:
    """Synthesise a complete OutGauge packet for tests."""
    body = struct.pack(
        PACKET_FORMAT,
        12345,                       # time_ms
        car.ljust(4, b"\x00"),       # car
        0,                           # flags
        gear,                        # gear
        0,                           # plid
        50.0,                        # speed_mps
        rpm,                         # rpm
        1.5,                         # turbo_bar
        90.0,                        # engine_temp
        0.5,                         # fuel
        4.0,                         # oil_pressure
        110.0,                       # oil_temp
        0,                           # dash_lights
        0,                           # show_lights
        throttle,                    # throttle
        brake,                       # brake
        0.0,                         # clutch
        display1.ljust(16, b"\x00"),
        display2.ljust(16, b"\x00"),
    )
    if with_id:
        body += struct.pack("<i", 7)
    return body


class FromBytesTests(unittest.TestCase):
    def test_decodes_92_byte_packet(self):
        pkt = OutGaugePacket.from_bytes(_make_packet(rpm=4321.0))
        self.assertIsNotNone(pkt)
        self.assertAlmostEqual(pkt.rpm, 4321.0, places=2)
        self.assertEqual(pkt.gear, 1)
        self.assertEqual(pkt.car, "GTR")
        self.assertEqual(pkt.id, None)

    def test_decodes_96_byte_packet_with_id(self):
        pkt = OutGaugePacket.from_bytes(_make_packet(rpm=8000.5, with_id=True))
        self.assertIsNotNone(pkt)
        self.assertAlmostEqual(pkt.rpm, 8000.5, places=2)
        self.assertEqual(pkt.id, 7)

    def test_rejects_unexpected_size(self):
        for size in (0, 32, 91, 93, 95, 97, 200):
            self.assertIsNone(OutGaugePacket.from_bytes(b"\x00" * size), size)

    def test_struct_format_size_matches_constant(self):
        self.assertEqual(struct.calcsize(PACKET_FORMAT), PACKET_SIZE)
        self.assertEqual(PACKET_SIZE + 4, PACKET_SIZE_WITH_ID)

    def test_zero_terminated_strings_are_trimmed(self):
        pkt = OutGaugePacket.from_bytes(_make_packet(
            display1=b"FUEL 0.50", display2=b"LAP 1:23.456",
        ))
        self.assertEqual(pkt.display1, "FUEL 0.50")
        self.assertEqual(pkt.display2, "LAP 1:23.456")

    def test_all_telemetry_fields_round_trip(self):
        # Sanity: every numeric field we care about is in the right slot.
        pkt = OutGaugePacket.from_bytes(_make_packet(rpm=6000, throttle=0.75,
                                                    brake=0.25, gear=3))
        self.assertAlmostEqual(pkt.throttle, 0.75, places=3)
        self.assertAlmostEqual(pkt.brake, 0.25, places=3)
        self.assertEqual(pkt.gear, 3)
        self.assertAlmostEqual(pkt.speed_mps, 50.0, places=2)
        self.assertAlmostEqual(pkt.fuel, 0.5, places=3)
        self.assertAlmostEqual(pkt.oil_pressure_bar, 4.0, places=3)
        self.assertAlmostEqual(pkt.engine_temp_c, 90.0, places=3)


class ToSampleTests(unittest.TestCase):
    def test_to_sample_carries_main_fields(self):
        pkt = OutGaugePacket.from_bytes(_make_packet(rpm=5500, gear=4,
                                                    throttle=0.9))
        sample = pkt.to_sample(timestamp=42.0)
        self.assertEqual(sample.timestamp, 42.0)
        self.assertAlmostEqual(sample.rpm, 5500, places=1)
        self.assertEqual(sample.gear, 4)
        self.assertAlmostEqual(sample.throttle, 0.9, places=3)
        self.assertEqual(sample.car, "GTR")

    def test_to_sample_with_id(self):
        pkt = OutGaugePacket.from_bytes(_make_packet(rpm=1, with_id=True))
        sample = pkt.to_sample(timestamp=0.0)
        self.assertEqual(sample.source_id, 7)


if __name__ == "__main__":
    unittest.main()
