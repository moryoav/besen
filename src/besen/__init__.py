"""Async Python client for Besen EV chargers."""

from __future__ import annotations

from .client import BesenClient
from .exceptions import (
    BesenError,
    CannotConnect,
    CommandFailed,
    InvalidAuth,
    NoConnectablePath,
    ProtocolError,
)
from .models import (
    BesenData,
    BoardRevision,
    CharacteristicPair,
    ChargerConfig,
    ChargerInfo,
    ChargeStatus,
    CommandResult,
)

__version__ = "0.4.2"

__all__ = [
    "BesenClient",
    "BesenData",
    "BesenError",
    "BoardRevision",
    "CannotConnect",
    "CharacteristicPair",
    "ChargeStatus",
    "ChargerConfig",
    "ChargerInfo",
    "CommandFailed",
    "CommandResult",
    "InvalidAuth",
    "NoConnectablePath",
    "ProtocolError",
]
