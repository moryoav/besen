"""Besen Home Assistant integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .const import CONF_SYNC_CLOCK, DEFAULT_SYNC_CLOCK, PLATFORMS

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from besen.client import BesenClient

    from .coordinator import BesenCoordinator


@dataclass(slots=True)
class BesenRuntimeData:
    """Runtime data for a Besen config entry."""

    client: BesenClient
    coordinator: BesenCoordinator


if TYPE_CHECKING:
    type BesenConfigEntry = ConfigEntry[BesenRuntimeData]
else:
    BesenConfigEntry = object

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BesenConfigEntry,
) -> bool:
    """Set up Besen from a config entry."""

    from homeassistant.components import bluetooth
    from homeassistant.const import CONF_ADDRESS, CONF_NAME, CONF_PIN
    from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

    from besen.client import BesenClient
    from besen.exceptions import CannotConnect, InvalidAuth

    from .coordinator import BesenCoordinator
    from .repairs import (
        async_create_no_connectable_path_issue,
        async_create_reauth_issue,
        async_delete_no_connectable_path_issue,
        async_delete_reauth_issue,
    )

    address = entry.data[CONF_ADDRESS]
    pin = entry.data[CONF_PIN]
    sync_clock = entry.options.get(
        CONF_SYNC_CLOCK,
        entry.data.get(CONF_SYNC_CLOCK, DEFAULT_SYNC_CLOCK),
    )

    def _ble_device_provider() -> BLEDevice | None:
        return bluetooth.async_ble_device_from_address(
            hass,
            address,
            connectable=True,
        )

    if _ble_device_provider() is None:
        async_create_no_connectable_path_issue(hass, entry.entry_id)
        reason = "No connectable Bluetooth path is available"
        diagnostics = getattr(
            bluetooth,
            "async_address_reachability_diagnostics",
            None,
        )
        intent = getattr(
            getattr(bluetooth, "BluetoothReachabilityIntent", object),
            "CONNECTION",
            None,
        )
        if callable(diagnostics) and intent is not None:
            reason = diagnostics(hass, address, intent)
        raise ConfigEntryNotReady(reason)

    client = BesenClient(
        address=address,
        pin=pin,
        ble_device_provider=_ble_device_provider,
        logger=_LOGGER,
        advertised_name=entry.data.get(CONF_NAME),
        sync_clock=sync_clock,
    )
    coordinator = BesenCoordinator(hass, client)

    try:
        await coordinator.async_start()
    except InvalidAuth as err:
        async_create_reauth_issue(hass, entry.entry_id)
        raise ConfigEntryAuthFailed from err
    except CannotConnect as err:
        async_create_no_connectable_path_issue(hass, entry.entry_id)
        raise ConfigEntryNotReady(str(err)) from err

    async_delete_no_connectable_path_issue(hass, entry.entry_id)
    async_delete_reauth_issue(hass, entry.entry_id)
    entry.runtime_data = BesenRuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: BesenConfigEntry,
) -> bool:
    """Unload a Besen config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.coordinator.async_shutdown()
    return unload_ok
