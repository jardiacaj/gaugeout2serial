"""TelemetrySource abstract base class."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..telemetry import TelemetrySample


class TelemetrySource(ABC):
    """A stream of telemetry samples (network protocol, shared memory, file replay…).

    Concrete sources own whatever I/O resource they need (UDP socket, mmap,
    file handle) and translate that resource's wire format into the
    sim-agnostic TelemetrySample dataclass.
    """

    name: str = "TelemetrySource"

    @abstractmethod
    def open(self) -> None:
        """Acquire I/O resources. Idempotent if already open."""

    @abstractmethod
    def close(self) -> None:
        """Release I/O resources. Idempotent if already closed."""

    @abstractmethod
    def poll(self, timeout: float) -> Optional[TelemetrySample]:
        """Block up to `timeout` seconds for the next sample.

        Returns None on timeout or on packets that fail to decode.
        """

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
