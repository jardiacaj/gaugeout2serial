# gaugeout2serial

[![CI](https://github.com/jardiacaj/gaugeout2serial/actions/workflows/ci.yml/badge.svg)](https://github.com/jardiacaj/gaugeout2serial/actions/workflows/ci.yml)

Bridge an OutGauge UDP telemetry stream (BeamNG.drive, LFS, anything that
emits the standard 92/96-byte OutGauge packet) to a serial-attached racing-
wheel dash on Linux.

OutGauge is the source-side common denominator. Each supported wheel speaks
its own serial dialect, so device-specific framing lives in its own module
(currently `protocol.py` for the Moza dash); adding a new wheel means adding
a new protocol/wheel module pair, not changing the receive loop.

Currently supported devices:

- **Moza R5** dash — 10-LED shift bar, 75 %–95 % solid, blink at 97 %.

The bar uses an autodiscovered redline: it tracks the highest RPM seen and
scales the bar to 95 % of that, resetting after 5 s of no engine RPM (so
swapping cars works without a restart). When the source is paused, the
engine is off, or no UDP packets are arriving at all, the bar flips to a
dedicated symmetric indicator so it's obvious the bridge is alive.

## Why

The Moza R5 dash is normally driven by Gudsen's Windows-only Pithouse
software. On Linux, [boxflat](https://github.com/Lawstorant/boxflat) reads
the wheel for joystick input but doesn't pipe game telemetry to the LEDs.
[monocoque](https://github.com/Spacefreak18/monocoque) gets close but
drives the dash through a memory-mapped daemon (`simd`) that needs a
patched build to detect BeamNG. This is the smaller alternative: a
~170-line Python script that listens on the OutGauge UDP socket and
writes the same Moza serial frames boxflat does.

## How it works

OutGauge is a fixed 92- or 96-byte UDP packet — same format LFS introduced
in 2002. Most modern sims (BeamNG, AC, ACC via plugins, LFS, rFactor 2 via
plugins) can emit it. We parse the f32 at offset 16 (engine RPM), convert
to a percent of the highest RPM seen so far, and write a Moza
`dash.send-telemetry` frame whose 4-byte payload is a per-LED bitmask the
firmware decodes directly.

State machine the wheel sees:

| condition | LEDs |
|-----------|------|
| active engine RPM | thermometer bar 75 %–95 %, blink at 97 % |
| OutGauge connected but engine off / paused (≥5 s of zero RPM) | LEDs 1 + 10 (extremes) |
| no UDP packet for >1 s | LEDs 5 + 6 (centre) |

The wheel firmware reverts to a slow-flash standby state if it stops
seeing writes for a few seconds, so the loop refreshes the current state
every iteration (≥1 Hz when idle, ≈packet rate when active).

## Requirements

### System

- **Linux.** Tested on Ubuntu 25.10. The bridge only writes to a
  `/dev/serial/by-id/...` device, so any OS with pyserial would work in
  theory — but the device path and permissions are Linux-specific.
- **No process holding `/dev/ttyACM0` exclusively.** If boxflat or
  monocoque is running and writing to the wheel, kill it first:
  ```bash
  pkill -f boxflat
  ```
  boxflat reading the wheel for joystick input is fine — it doesn't
  collide with our writes.

### Python

- Python 3.11+
- `pyserial` (only runtime dep)

### Hardware

- Moza R5 wheelbase with the dash module, plugged in over USB.
- The default device path is the by-id symlink for one specific R5; pass
  `--devpath` to override.

### Sim

Anything that emits OutGauge UDP. For BeamNG.drive, enable it under
*Options → Others → OutGauge*. The bridge defaults to UDP port `4444`;
match whatever you set in the sim, or pass `--port`.

## Quick start

```bash
git clone https://github.com/jardiacaj/gaugeout2serial.git
cd gaugeout2serial
pip install -e .
gaugeout2serial -v
```

You should see:

1. A 2-second single-LED sweep on the wheel (the startup self-test).
2. `LEDs 5+6` lit until the first OutGauge packet arrives.
3. The bar tracking RPM once you go to gameplay with an engine on.

## CLI

```
gaugeout2serial [options]

  --devpath PATH    serial device path of the wheel
                    (default: /dev/serial/by-id/usb-Gudsen_MOZA_R5_Base_…)
  --baud N          serial baud rate (default 115200)
  --host HOST       UDP host to bind for OutGauge (default 0.0.0.0)
  --port N          OutGauge UDP port (default 4444)
  -v, --verbose     print rpm/pct/mask once per second + state transitions
```

## Acknowledgements

The Moza serial framing and the LED bitmask encoding were reverse-engineered
in the [boxflat](https://github.com/Lawstorant/boxflat) and
[monocoque](https://github.com/Spacefreak18/monocoque) projects. This bridge
just glues the two protocols (LFS OutGauge + Moza dash serial) together.

## License

[MIT](LICENSE).
