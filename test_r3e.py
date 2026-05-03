"""Tests for the R3E shared-memory UDP packet decoder."""
import math
import struct
import unittest

from gaugeout2serial.sources.r3e import (
    R3E_MIN_PACKET_SIZE,
    R3EPacket,
    rps_to_rpm,
    OFF_BRAKE,
    OFF_CAR_SPEED,
    OFF_CLUTCH,
    OFF_ENGINE_OIL_PRESSURE,
    OFF_ENGINE_OIL_TEMP,
    OFF_ENGINE_RPS,
    OFF_ENGINE_TEMP,
    OFF_FUEL_CAPACITY,
    OFF_FUEL_LEFT,
    OFF_GAME_IN_MENUS,
    OFF_GAME_IN_REPLAY,
    OFF_GAME_PAUSED,
    OFF_GEAR,
    OFF_MAX_ENGINE_RPS,
    OFF_NUM_GEARS,
    OFF_THROTTLE,
    OFF_UPSHIFT_RPS,
    OFF_VERSION_MAJOR,
    OFF_VERSION_MINOR,
)


def _rpm_to_rps(rpm: float) -> float:
    return rpm * (2.0 * math.pi) / 60.0


def _make_packet(
    *,
    engine_rpm: float = 4000.0,
    max_engine_rpm: float = 8000.0,
    upshift_rpm: float = 7800.0,
    gear: int = 2,
    num_gears: int = 6,
    throttle: float = 0.5,
    brake: float = 0.0,
    clutch: float = 0.0,
    car_speed_mps: float = 50.0,
    fuel_left: float = 30.0,
    fuel_capacity: float = 60.0,
    engine_temp_c: float = 95.0,
    oil_temp_c: float = 105.0,
    oil_pressure_bar: float = 4.5,
    paused: bool = False,
    in_menus: bool = False,
    in_replay: bool = False,
    version: tuple = (2, 11),
    size: int = R3E_MIN_PACKET_SIZE,
) -> bytes:
    buf = bytearray(size)
    struct.pack_into("<i", buf, OFF_VERSION_MAJOR, version[0])
    struct.pack_into("<i", buf, OFF_VERSION_MINOR, version[1])
    struct.pack_into("<i", buf, OFF_GAME_PAUSED, int(paused))
    struct.pack_into("<i", buf, OFF_GAME_IN_MENUS, int(in_menus))
    struct.pack_into("<i", buf, OFF_GAME_IN_REPLAY, int(in_replay))
    struct.pack_into("<f", buf, OFF_CAR_SPEED, car_speed_mps)
    struct.pack_into("<f", buf, OFF_ENGINE_RPS, _rpm_to_rps(engine_rpm))
    struct.pack_into("<f", buf, OFF_MAX_ENGINE_RPS, _rpm_to_rps(max_engine_rpm))
    struct.pack_into("<f", buf, OFF_UPSHIFT_RPS, _rpm_to_rps(upshift_rpm))
    struct.pack_into("<i", buf, OFF_GEAR, gear)
    struct.pack_into("<i", buf, OFF_NUM_GEARS, num_gears)
    struct.pack_into("<f", buf, OFF_FUEL_LEFT, fuel_left)
    struct.pack_into("<f", buf, OFF_FUEL_CAPACITY, fuel_capacity)
    struct.pack_into("<f", buf, OFF_ENGINE_TEMP, engine_temp_c)
    struct.pack_into("<f", buf, OFF_ENGINE_OIL_TEMP, oil_temp_c)
    struct.pack_into("<f", buf, OFF_ENGINE_OIL_PRESSURE, oil_pressure_bar)
    struct.pack_into("<f", buf, OFF_THROTTLE, throttle)
    struct.pack_into("<f", buf, OFF_BRAKE, brake)
    struct.pack_into("<f", buf, OFF_CLUTCH, clutch)
    return bytes(buf)


class FromBytesTests(unittest.TestCase):
    def test_decodes_minimal_packet(self):
        pkt = R3EPacket.from_bytes(_make_packet(engine_rpm=5500.0))
        self.assertIsNotNone(pkt)
        self.assertAlmostEqual(pkt.engine_rpm, 5500.0, places=1)
        self.assertEqual(pkt.gear, 2)
        self.assertEqual(pkt.version_major, 2)

    def test_rejects_short_packet(self):
        self.assertIsNone(R3EPacket.from_bytes(b"\x00" * (R3E_MIN_PACKET_SIZE - 1)))
        self.assertIsNone(R3EPacket.from_bytes(b""))

    def test_rps_conversion_matches_known_values(self):
        # 8000 rpm = 837.758 rad/s; round-trip through both functions.
        self.assertAlmostEqual(rps_to_rpm(_rpm_to_rps(8000.0)), 8000.0, places=2)

    def test_decodes_full_telemetry(self):
        pkt = R3EPacket.from_bytes(_make_packet(
            engine_rpm=6000.0, max_engine_rpm=8500.0, upshift_rpm=8200.0,
            gear=4, num_gears=7, throttle=0.9, brake=0.1, clutch=0.0,
            car_speed_mps=70.0, fuel_left=20.0, fuel_capacity=80.0,
            engine_temp_c=92.5, oil_temp_c=110.0, oil_pressure_bar=5.0,
        ))
        self.assertAlmostEqual(pkt.engine_rpm, 6000.0, places=1)
        self.assertAlmostEqual(pkt.max_engine_rpm, 8500.0, places=1)
        self.assertAlmostEqual(pkt.upshift_rpm, 8200.0, places=1)
        self.assertEqual(pkt.gear, 4)
        self.assertEqual(pkt.num_gears, 7)
        self.assertAlmostEqual(pkt.throttle, 0.9, places=3)
        self.assertAlmostEqual(pkt.brake, 0.1, places=3)
        self.assertAlmostEqual(pkt.car_speed_mps, 70.0, places=2)
        self.assertAlmostEqual(pkt.fuel_left, 20.0, places=2)
        self.assertAlmostEqual(pkt.engine_temp_c, 92.5, places=2)


class ToSampleTests(unittest.TestCase):
    def test_sample_uses_upshift_rpm_as_max(self):
        pkt = R3EPacket.from_bytes(_make_packet(
            max_engine_rpm=9000.0, upshift_rpm=8500.0,
        ))
        sample = pkt.to_sample(timestamp=0.0)
        self.assertAlmostEqual(sample.max_rpm, 8500.0, places=1)

    def test_falls_back_to_max_engine_rpm_when_no_upshift(self):
        pkt = R3EPacket.from_bytes(_make_packet(
            max_engine_rpm=9000.0, upshift_rpm=0.0,
        ))
        sample = pkt.to_sample(timestamp=0.0)
        self.assertAlmostEqual(sample.max_rpm, 9000.0, places=1)

    def test_gear_na_becomes_none(self):
        pkt = R3EPacket.from_bytes(_make_packet(gear=-2))
        sample = pkt.to_sample(timestamp=0.0)
        self.assertIsNone(sample.gear)

    def test_negative_engine_rpm_is_none(self):
        pkt = R3EPacket.from_bytes(_make_packet(engine_rpm=-1.0))
        sample = pkt.to_sample(timestamp=0.0)
        self.assertIsNone(sample.rpm)

    def test_fuel_fraction_computed(self):
        pkt = R3EPacket.from_bytes(_make_packet(fuel_left=15.0, fuel_capacity=60.0))
        sample = pkt.to_sample(timestamp=0.0)
        self.assertAlmostEqual(sample.fuel, 0.25, places=3)

    def test_fuel_capacity_zero_leaves_fuel_none(self):
        pkt = R3EPacket.from_bytes(_make_packet(fuel_left=0.0, fuel_capacity=0.0))
        sample = pkt.to_sample(timestamp=0.0)
        self.assertIsNone(sample.fuel)

    def test_sample_carries_full_r3e_field_set(self):
        pkt = R3EPacket.from_bytes(_make_packet(
            engine_rpm=6000.0, max_engine_rpm=8500.0, upshift_rpm=8200.0,
            gear=3, num_gears=6, throttle=0.7, brake=0.2, clutch=0.05,
            car_speed_mps=42.0, fuel_left=24.0, fuel_capacity=70.0,
            engine_temp_c=88.0, oil_temp_c=102.0, oil_pressure_bar=4.0,
            paused=False, in_menus=True, in_replay=False,
        ))
        sample = pkt.to_sample(timestamp=0.0)
        self.assertAlmostEqual(sample.rpm, 6000.0, places=1)
        self.assertAlmostEqual(sample.max_rpm, 8200.0, places=1)
        self.assertAlmostEqual(sample.upshift_rpm, 8200.0, places=1)
        self.assertEqual(sample.gear, 3)
        self.assertEqual(sample.num_gears, 6)
        self.assertAlmostEqual(sample.throttle, 0.7, places=3)
        self.assertAlmostEqual(sample.brake, 0.2, places=3)
        self.assertAlmostEqual(sample.clutch, 0.05, places=3)
        self.assertAlmostEqual(sample.speed_mps, 42.0, places=2)
        self.assertAlmostEqual(sample.fuel, 24.0 / 70.0, places=4)
        self.assertAlmostEqual(sample.fuel_litres, 24.0, places=2)
        self.assertAlmostEqual(sample.fuel_capacity_litres, 70.0, places=2)
        self.assertAlmostEqual(sample.engine_temp_c, 88.0, places=2)
        self.assertAlmostEqual(sample.oil_temp_c, 102.0, places=2)
        self.assertAlmostEqual(sample.oil_pressure_bar, 4.0, places=2)
        self.assertFalse(sample.game_paused)
        self.assertTrue(sample.game_in_menus)
        self.assertFalse(sample.game_in_replay)

    def test_sample_game_state_flags(self):
        pkt = R3EPacket.from_bytes(_make_packet(
            paused=True, in_menus=True, in_replay=True,
        ))
        sample = pkt.to_sample(timestamp=0.0)
        self.assertTrue(sample.game_paused)
        self.assertTrue(sample.game_in_menus)
        self.assertTrue(sample.game_in_replay)

    def test_num_gears_negative_becomes_none(self):
        pkt = R3EPacket.from_bytes(_make_packet(num_gears=-1))
        sample = pkt.to_sample(timestamp=0.0)
        self.assertIsNone(sample.num_gears)

    def test_upshift_rpm_zero_becomes_none(self):
        pkt = R3EPacket.from_bytes(_make_packet(upshift_rpm=0.0,
                                                max_engine_rpm=9000.0))
        sample = pkt.to_sample(timestamp=0.0)
        self.assertIsNone(sample.upshift_rpm)
        self.assertAlmostEqual(sample.max_rpm, 9000.0, places=1)


if __name__ == "__main__":
    unittest.main()
