"""Device abstract base class + DeviceState enum."""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import List

from ..telemetry import TelemetrySample


class DeviceState(Enum):
    """Coarse output state the bridge derives from the telemetry stream.

    Each device chooses how to render each state visually/haptically.
    """

    NO_DATA = "no_data"      # source silent for >DARK_AFTER seconds
    IDLE = "idle"            # source alive but engine off / paused
    TELEMETRY = "telemetry"  # active engine RPM


class Device(ABC):
    """A telemetry-driven hardware device."""

    name: str = "Device"

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def startup_indicator(self) -> None:
        """One-shot self-test pattern shown right after open(), before any
        telemetry has arrived. Confirms the device-write path is alive."""

    @abstractmethod
    def show_no_data(self) -> None: ...

    @abstractmethod
    def show_idle(self) -> None: ...

    @abstractmethod
    def show_telemetry(self, sample: TelemetrySample, full_scale_rpm: float) -> None:
        """Render a live sample. `full_scale_rpm` is the bridge's current
        autodiscovered redline (the value at which the bar should be full)."""

    def heartbeat(self) -> None:
        """Optional periodic refresh — e.g., re-send mode-set frames so the
        device firmware doesn't time out and revert to standby. No-op default."""

    @classmethod
    def discover(cls) -> List["Device"]:
        """Return Device instances for any auto-detected hardware of this
        type. Default returns an empty list; subclasses override to scan
        sysfs / /dev/serial/by-id / USB / etc."""
        return []

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
