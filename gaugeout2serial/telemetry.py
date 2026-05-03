"""
Sim-agnostic telemetry sample.

Produced by a TelemetrySource, consumed by a Device. Every field except
`timestamp` is optional — different sources publish different subsets,
and devices ignore what they don't render.

Each field's comment ends with the list of sources that populate it
today. Sources that don't appear there leave the field at None.

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
    timestamp: float
    """Monotonic seconds when the sample was received. [OutGauge, R3E]"""

    # ── Engine ────────────────────────────────────────────────────────────
    rpm: Optional[float] = None
    """Engine speed in RPM. [OutGauge, R3E]"""

    max_rpm: Optional[float] = None
    """Redline / engine limiter the bar should treat as full-scale.
    R3E publishes this per-car (uses `upshift_rpm` when available, else
    `max_engine_rps`). OutGauge has no equivalent — when this is None the
    bridge falls back to autodiscovered peak. [R3E]"""

    upshift_rpm: Optional[float] = None
    """Recommended shift point for the current car, distinct from the
    redline. [R3E]"""

    gear: Optional[int] = None
    """Current gear: -1 = reverse, 0 = neutral, 1..N = forward gears.
    Sources convert from their native encoding (OutGauge: 0=R/1=N/2=1st,
    R3E: -2=N/A/-1=R/0=N/1=1st). [OutGauge, R3E]"""

    num_gears: Optional[int] = None
    """Number of forward gears in the current car's gearbox. [R3E]"""

    speed_mps: Optional[float] = None
    """Vehicle speed in metres per second. [OutGauge, R3E]"""

    throttle: Optional[float] = None
    """Throttle pedal position, 0..1. [OutGauge, R3E]"""

    brake: Optional[float] = None
    """Brake pedal position, 0..1. [OutGauge, R3E]"""

    clutch: Optional[float] = None
    """Clutch pedal position, 0..1. [OutGauge, R3E]"""

    # ── Fuel ──────────────────────────────────────────────────────────────
    fuel: Optional[float] = None
    """Fuel remaining as a 0..1 fraction of capacity. [OutGauge, R3E]"""

    fuel_litres: Optional[float] = None
    """Absolute fuel remaining in litres. [R3E]"""

    fuel_capacity_litres: Optional[float] = None
    """Tank capacity in litres. [R3E]"""

    # ── Diagnostics ───────────────────────────────────────────────────────
    turbo_bar: Optional[float] = None
    """Turbo boost pressure in bar. [OutGauge]"""

    engine_temp_c: Optional[float] = None
    """Engine (water) temperature in °C. [OutGauge, R3E]"""

    oil_pressure_bar: Optional[float] = None
    """Engine oil pressure in bar. [OutGauge, R3E]"""

    oil_temp_c: Optional[float] = None
    """Engine oil temperature in °C. [OutGauge, R3E]"""

    # ── Warning lights ────────────────────────────────────────────────────
    dash_lights: Optional[int] = None
    """Bitmask of *available* dash warning lights for the current car
    (OG_DL_* bits — shift, full-beam, handbrake, pit-speed, TC, signals,
    oil, battery, ABS, spare). [OutGauge]"""

    show_lights: Optional[int] = None
    """Bitmask of dash warning lights *currently lit* (same bit layout as
    `dash_lights`). [OutGauge]"""

    # ── Game / session state ──────────────────────────────────────────────
    game_paused: Optional[bool] = None
    """True if the sim is paused. [R3E]"""

    game_in_menus: Optional[bool] = None
    """True if the player is currently in menus rather than driving. [R3E]"""

    game_in_replay: Optional[bool] = None
    """True if the sim is showing a replay rather than live driving. [R3E]"""

    control_type: Optional[int] = None
    """Who is driving the vehicle right now. Values are source-specific
    (R3E: r3e_control enum — player, AI, remote, replay, …). [R3E]"""

    # ── Identifiers / display strings ─────────────────────────────────────
    car: Optional[str] = None
    """Short car-name tag (4-character LFS abbreviation). [OutGauge]"""

    flags: Optional[int] = None
    """Raw OutGauge flags bitfield (OG_SHIFT, OG_CTRL, OG_TURBO, OG_KM,
    OG_BAR). Decode with `OutGaugeFlag` or the boolean accessors on
    `OutGaugePacket`. [OutGauge]"""

    player_id: Optional[int] = None
    """Unique ID of the viewed player (0 = none). [OutGauge]"""

    display1: Optional[str] = None
    """Sim-chosen display string, typically a fuel readout. [OutGauge]"""

    display2: Optional[str] = None
    """Sim-chosen display string, typically a settings / lap readout. [OutGauge]"""

    source_id: Optional[int] = None
    """Optional packet-instance ID — only present in 96-byte OutGauge
    packets where the sim has been configured with an `OutGaugeID`.
    [OutGauge]"""
