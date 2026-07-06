"""Exceptions raised by the Besen integration."""


class BesenError(Exception):
    """Base class for Besen errors."""


class CannotConnect(BesenError):
    """Raised when the charger cannot be reached."""


class NoConnectablePath(CannotConnect):
    """Raised when Home Assistant has no active Bluetooth path to the charger."""


class InvalidAuth(BesenError):
    """Raised when the charger rejects the PIN."""


class ProtocolError(BesenError):
    """Raised when charger data is malformed."""


class CommandFailed(BesenError):
    """Raised when a charger command fails."""
