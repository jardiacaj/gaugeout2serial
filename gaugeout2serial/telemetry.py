"""
Sim-agnostic telemetry sample.

Produced by a TelemetrySource, consumed by a Device. Every field except
`timestamp` is optional — different sources publish different subsets,
and devices ignore what they don't render.

Conventions:
- All numeric fields are SI / sim-spec units encoded in the field name
  (e.g. `_mps`, `_rpm`, `_c`, `_bar`, `_litres`).
- `gear`: -1 = reverse, 0 = neutral, 1..N = forward gears, None = N/A.
  Sources normalise their native encoding to this convention.
- Fractional inputs (`throttle`, `brake`, `clutch`, `fuel`) are 0..1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TelemetrySample:
    timestamp: float                            # monotonic seconds when received

    # Engine
    rpm: Optional[float] = None
    max_rpm: Optional[float] = None             # redline / limiter
    upshift_rpm: Optional[float] = None         # per-car shift hint, if any
    gear: Optional[int] = None                  # -1=R, 0=N, 1..N forward
    num_gears: Optional[int] = None
    speed_mps: Optional[float] = None
    throttle: Optional[float] = None            # 0..1
    brake: Optional[float] = None               # 0..1
    clutch: Optional[float] = None              # 0..1

    # Fuel — `fuel` is the 0..1 fraction (OutGauge style); the absolute
    # amounts are populated when the source provides them (e.g. R3E).
    fuel: Optional[float] = None                # 0..1
    fuel_litres: Optional[float] = None
    fuel_capacity_litres: Optional[float] = None

    # Diagnostics
    turbo_bar: Optional[float] = None
    engine_temp_c: Optional[float] = None
    oil_pressure_bar: Optional[float] = None
    oil_temp_c: Optional[float] = None

    # Warning lights bitmasks (bit layout is source-dependent)
    dash_lights: Optional[int] = None
    show_lights: Optional[int] = None

    # Game / session state. Each is True/False/None — None when the
    # source doesn't surface it.
    game_paused: Optional[bool] = None
    game_in_menus: Optional[bool] = None
    game_in_replay: Optional[bool] = None
    control_type: Optional[int] = None          # who's driving (source-specific enum)

    # Identifiers / display strings
    car: Optional[str] = None
    flags: Optional[int] = None
    player_id: Optional[int] = None
    display1: Optional[str] = None
    display2: Optional[str] = None
    source_id: Optional[int] = None
