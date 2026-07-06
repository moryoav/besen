"""Shared pytest setup."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any, cast


def _install_bluetooth_stub() -> None:
    """Install a lightweight Bluetooth module stub for unit tests."""

    if "homeassistant.components.bluetooth" in sys.modules:
        return

    bluetooth = ModuleType("homeassistant.components.bluetooth")

    class BluetoothServiceInfoBleak:
        """Stub discovery info type."""

    def async_ble_device_from_address(*args: Any, **kwargs: Any) -> None:
        """Return no BLE device by default."""

        del args, kwargs

    async def async_request_active_scan(*args: Any, **kwargs: Any) -> None:
        """Stub active scan request."""

        del args, kwargs

    bluetooth_any = cast(Any, bluetooth)
    bluetooth_any.BluetoothServiceInfoBleak = BluetoothServiceInfoBleak
    bluetooth_any.BluetoothReachabilityIntent = SimpleNamespace(CONNECTION="connection")
    bluetooth_any.async_ble_device_from_address = async_ble_device_from_address
    bluetooth_any.async_request_active_scan = async_request_active_scan
    bluetooth_any.async_address_reachability_diagnostics = lambda *args, **kwargs: (
        "No connectable Bluetooth path is available"
    )
    sys.modules["homeassistant.components.bluetooth"] = bluetooth


_install_bluetooth_stub()
