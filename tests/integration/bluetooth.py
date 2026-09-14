"""Bluetooth test data helpers adapted from Home Assistant Core."""

from typing import Any

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData


def generate_advertisement_data(**kwargs: Any) -> AdvertisementData:
    """Generate advertisement data with defaults."""
    values: dict[str, Any] = {
        "local_name": "",
        "manufacturer_data": {},
        "service_data": {},
        "service_uuids": [],
        "rssi": -127,
        "platform_data": ((),),
        "tx_power": -127,
    }
    values.update(kwargs)
    return AdvertisementData(**values)


def generate_ble_device(address: str, name: str | None = None) -> BLEDevice:
    """Generate a BLE device without using an adapter."""
    return BLEDevice(address, name, None)
