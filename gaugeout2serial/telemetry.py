"""
Sim-agnostic telemetry sample.

Produced by a TelemetrySource, consumed by a Device. Every field except
`timestamp` is optional — different sources publish different subsets, and
devices ignore what they don't render.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TelemetrySample:
    timestamp: float                        # monotonic seconds when received

    # Engine
    rpm: Optional[float] = None
    max_rpm: Optional[float] = None         # if the source publishes a redline
    gear: Optional[int] = None              # 0=R, 1=N, 2=1st, ...
    speed_mps: Optional[float] = None
    throttle: Optional[float] = None        # 0..1
    brake: Optional[float] = None
    clutch: Optional[float] = None
    fuel: Optional[float] = None            # 0..1

    # Diagnostics
    turbo_bar: Optional[float] = None
    engine_temp_c: Optional[float] = None
    oil_pressure_bar: Optional[float] = None
    oil_temp_c: Optional[float] = None

    # Warning lights bitmasks (bit layout is source-dependent)
    dash_lights: Optional[int] = None
    show_lights: Optional[int] = None

    # Identifiers / display strings
    car: Optional[str] = None
    flags: Optional[int] = None
    player_id: Optional[int] = None
    display1: Optional[str] = None
    display2: Optional[str] = None
    source_id: Optional[int] = None
