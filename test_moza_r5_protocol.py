"""Pure-function tests for the Moza R5 framing layer. No serial I/O."""
import unittest

from gaugeout2serial.devices.moza_r5 import protocol


class FrameTests(unittest.TestCase):
    def test_telemetry_frame_byte_for_byte(self):
        # Reference frame: zero-rpm telemetry. csum = (13 + sum(0x7e..0x00)) % 256.
        f = protocol.telemetry_frame(bytes([0, 0, 0, 0]))
        self.assertEqual(
            f.hex(),
            "7e0641" "12" "fdde" "00000000" "bf",
        )

    def test_checksum_invariant(self):
        # csum byte equals (MAGIC + sum(prev_bytes)) % 256 by definition.
        for payload in (b"\x00\x00\x00\x00", b"\xff\xff\xff\xff", b"\x12\x34\x56\x78"):
            f = protocol.telemetry_frame(payload)
            csum = f[-1]
            expected = (protocol.MAGIC + sum(f[:-1])) % 256
            self.assertEqual(csum, expected, payload.hex())

    def test_indicator_mode_frame_lengths(self):
        # length byte = payload + id_bytes; here 1 + 2 = 3
        f = protocol.indicator_mode_frame(1)
        self.assertEqual(f[0], protocol.START)
        self.assertEqual(f[1], 3)

    def test_rpm_mode_frame_lengths(self):
        f = protocol.rpm_mode_frame(0)
        self.assertEqual(f[0], protocol.START)
        self.assertEqual(f[1], 2)  # 1 byte payload + 1 byte id

    def test_telemetry_frame_rejects_wrong_payload_length(self):
        with self.assertRaises(ValueError):
            protocol.telemetry_frame(bytes([0, 0, 0]))


class BitmaskTests(unittest.TestCase):
    def test_below_first_threshold_is_dark(self):
        for pct in (0, 25, 50, 74):
            self.assertEqual(protocol.build_bitmask(pct), bytes([0, 0, 0, 0]), pct)

    def test_first_led_lights_at_75(self):
        self.assertEqual(protocol.build_bitmask(75), bytes([0, 0, 0, 0x01]))

    def test_full_bar_below_blink(self):
        # pct=96: all 10 LEDs on, blink not yet.
        self.assertEqual(protocol.build_bitmask(96), bytes([0, 0, 0x03, 0xFF]))

    def test_blink_bit_at_97(self):
        self.assertEqual(protocol.build_bitmask(97), bytes([0, 0, 0x83, 0xFF]))

    def test_clamped_above_redline(self):
        self.assertEqual(protocol.build_bitmask(120), bytes([0, 0, 0x83, 0xFF]))

    def test_thresholds_are_monotonic(self):
        # Bit count should never decrease as pct increases (until clamp).
        prev_bits = 0
        for pct in range(0, 101):
            mask = protocol.build_bitmask(pct)
            bits = bin(int.from_bytes(mask, "big")).count("1")
            self.assertGreaterEqual(bits, prev_bits, pct)
            prev_bits = bits


class SingleLedTests(unittest.TestCase):
    def test_leds_1_through_8_in_byte9(self):
        for n in range(1, 9):
            mask = protocol.single_led_mask(n)
            self.assertEqual(mask[2], 0x00)
            self.assertEqual(mask[3], 1 << (n - 1))

    def test_led_9_in_byte8_bit0(self):
        self.assertEqual(protocol.single_led_mask(9), bytes([0, 0, 0x01, 0x00]))

    def test_led_10_in_byte8_bit1(self):
        self.assertEqual(protocol.single_led_mask(10), bytes([0, 0, 0x02, 0x00]))

    def test_out_of_range_returns_dark(self):
        self.assertEqual(protocol.single_led_mask(0), bytes([0, 0, 0, 0]))
        self.assertEqual(protocol.single_led_mask(11), bytes([0, 0, 0, 0]))


class IndicatorPayloadTests(unittest.TestCase):
    def test_no_data_lights_leds_5_and_6(self):
        # LED 5 = byte9 bit 4 (0x10); LED 6 = byte9 bit 5 (0x20). 0x10|0x20 = 0x30.
        self.assertEqual(protocol.NO_DATA_PAYLOAD, bytes([0, 0, 0, 0x30]))

    def test_zero_only_lights_leds_1_and_10(self):
        # LED 1 = byte9 bit 0 (0x01); LED 10 = byte8 bit 1 (0x02).
        self.assertEqual(protocol.ZERO_ONLY_PAYLOAD, bytes([0, 0, 0x02, 0x01]))


if __name__ == "__main__":
    unittest.main()
