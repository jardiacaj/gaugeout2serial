# Contributing to gaugeout2serial

## Prerequisites

- Linux (tested on Ubuntu 25.10)
- Python 3.11+
- A Moza R5 with the dash module, or any OutGauge-emitting sim if you only
  want to exercise the parser path

## Clone and run

```bash
git clone https://github.com/jardiacaj/gaugeout2serial.git
cd gaugeout2serial
pip install -e .
gaugeout2serial -v
```

`pip install -e .` is needed because `pyserial` is not in the standard
library. Everything else is stdlib.

## Running tests

```bash
python3 -m unittest discover -v
```

The tests cover the pure-function layers (Moza framing, bitmask thresholds,
OutGauge packet parsing) — no wheel hardware required. Hardware-dependent
paths in `wheel.py` and the live UDP loop in `cli.py` are tested manually.

## Coding style

- PEP 8, 100-column soft limit.
- Keep `protocol.py` free of I/O — it's the layer with the most invariants
  and the easiest to fuzz, so it stays a pure-function module.
- Wheel writes go through `wheel.py`. UDP through `outgauge.py`. The CLI
  loop in `cli.py` should not touch `serial.Serial` or `socket` directly.

## Contributor License Agreement

By submitting a pull request you agree that your contribution is licensed
under the same [MIT License](LICENSE) that covers this project. See
[CLA.md](CLA.md) for details.

## Pull request process

1. Fork the repository and create a branch from `main`.
2. Make your changes and ensure `python3 -m unittest discover -v` passes.
3. Add or update tests if the change affects behaviour.
4. Update `README.md` if any CLI flags changed.
5. Open a pull request against `main`.

## Platform note

gaugeout2serial is Linux-first. The serial-write path depends on
`pyserial` and a `/dev/serial/by-id/...` device path; ports to other
platforms are welcome but must not break the Linux path.
