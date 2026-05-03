# gaugeout2serial

[![CI](https://github.com/jardiacaj/gaugeout2serial/actions/workflows/ci.yml/badge.svg)](https://github.com/jardiacaj/gaugeout2serial/actions/workflows/ci.yml)

Bridge sim-racing telemetry to a serial-attached racing-wheel dash on Linux.

Telemetry comes in over UDP from any of the supported sources, gets
normalised into a sim-agnostic `TelemetrySample`, and is written out as
the device-specific serial frames each wheel expects.

Currently supported sources:

- **OutGauge UDP** — BeamNG.drive, LFS, and anything else that emits the
  standard 92/96-byte LFS-format packet.
- **R3E (RaceRoom)** — RaceRoom doesn't emit UDP natively; you run a
  Windows-side `shmem→UDP` relay inside the same Proton/Wine prefix as
  the game and point this source at the relay's port.

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
- Auto-discovered by scanning `/dev/serial/by-id/` for
  `usb-Gudsen_MOZA_R5_Base_*`. Pass `--moza-r5-devpath PATH` if you want
  to override.

### Sim

**OutGauge sims** (BeamNG.drive, LFS, …) — enable OutGauge in the sim's
options. The bridge defaults to UDP port `4444`; match whatever you set
in the sim, or pass `--outgauge-port`.

**RaceRoom (R3E)** — RaceRoom only exposes telemetry via Windows shared
memory, so on Linux you need a relay inside the Proton prefix:

1. Find the prefix: Steam app id `211500`, located at
   `~/.local/share/Steam/steamapps/compatdata/211500/pfx`
   (or `~/.steam/steam/...` depending on your Steam install).
2. Drop a Windows R3E shmem→UDP relay (e.g. OverTake's
   *Telemetry Tool for R3E*) into `pfx/drive_c/relay/`.
3. Install `protontricks` (`apt install protontricks` or the Flatpak).
4. Start RaceRoom from Steam, then in a terminal:
   ```bash
   protontricks-launch --appid 211500 \
     ~/.local/share/Steam/steamapps/compatdata/211500/pfx/drive_c/relay/relay.exe \
     --send 127.0.0.1:6000
   ```
   The exact `--send` flag depends on the relay; check its docs.
5. Run the bridge in R3E mode:
   ```bash
   gaugeout2serial --source r3e --r3e-port 6000
   ```

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

### Wrap a game (mangohud / gamemoderun style)

`gaugeout2serial` can also wrap the game command, so the bridge starts
when the game does and exits when the game exits — drop-in compatible
with Steam launch options.

Standalone:
```bash
gaugeout2serial -- /path/to/BeamNG.drive --some-arg
```

Steam launch options:
```
gaugeout2serial -- %command%
```

Stack with other wrappers:
```
gamemoderun gaugeout2serial -- %command%
```

The wrapper forwards `SIGINT` and `SIGTERM` to the child, so Ctrl+C in
the terminal still reaches the game; the bridge cleans up the wheel
state and propagates the game's exit code as its own.

## CLI

```
gaugeout2serial [options]

  source:
    --source {outgauge,r3e}     telemetry source (default outgauge)
    --outgauge-host HOST        OutGauge UDP host (default 0.0.0.0)
    --outgauge-port N           OutGauge UDP port (default 4444)
    --r3e-host HOST             R3E relay UDP host (default 0.0.0.0)
    --r3e-port N                R3E relay UDP port (default 6000)

  devices:
    --moza-r5-devpath PATH      explicit Moza R5 serial path
                                (default: auto-discover via /dev/serial/by-id/)
    --moza-r5-baud N            Moza R5 baud rate (default 115200)
    --list-devices              list auto-discovered devices and exit

  -v, --verbose                 print state transitions and per-second
                                telemetry summaries
```

## Architecture

```
sources/                   ← produce TelemetrySample
  base.TelemetrySource       (ABC)
  outgauge.OutGaugeSource    (UDP — current)
                              + OutGaugePacket (full LFS-format decoder)

devices/                   ← consume TelemetrySample / DeviceState
  base.Device                (ABC) + DeviceState enum
  discovery.auto_discover_devices()
  moza_r5/                   ← first supported device
    device.MozaR5              (Device implementation)
    protocol.py                (frame builder + LED bitmasks)

bridge.Bridge              ← state machine, source → devices fan-out
cli.main                   ← arg parsing + glue
telemetry.TelemetrySample  ← sim-agnostic sample passed source → device
```

Adding a new source means subclassing `TelemetrySource` and producing
`TelemetrySample`s. Adding a new device means subclassing `Device` and
implementing the four `show_*` / `startup_indicator` methods plus a
`discover()` classmethod for autodetection.

## Acknowledgements

The Moza serial framing and the LED bitmask encoding were reverse-engineered
in the [boxflat](https://github.com/Lawstorant/boxflat) and
[monocoque](https://github.com/Spacefreak18/monocoque) projects. This bridge
just glues the two protocols (LFS OutGauge + Moza dash serial) together.

## License

[MIT](LICENSE).
