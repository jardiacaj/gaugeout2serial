"""Moza R5 wheel dash device + serial protocol primitives."""
from .device import MozaR5
from . import protocol

__all__ = ["MozaR5", "protocol"]
