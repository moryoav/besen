"""Coordinator for Besen push updates."""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from besen.client import BesenClient
from besen.exceptions import CommandFailed
from besen.models import BesenData

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class BesenCoordinator(DataUpdateCoordinator[BesenData]):
    """Coordinate Besen state updates."""

    def __init__(self, hass: HomeAssistant, client: BesenClient) -> None:
        """Initialize the coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_method=self._async_update_data,
        )
        self.client = client
        self._remove_listener: Callable[[], None] | None = None

    async def async_start(self) -> None:
        """Start listening to charger updates."""

        self._remove_listener = self.client.add_listener(self._handle_client_update)
        await self.client.async_start()
        self.async_set_updated_data(self.client.state)

    async def async_shutdown(self) -> None:
        """Stop listening to charger updates."""

        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        await self.client.async_stop()

    async def _async_update_data(self) -> BesenData:
        """Return latest push state for manual refresh requests."""

        return self.client.state

    @callback
    def _handle_client_update(self, data: BesenData) -> None:
        """Publish a client state update."""

        self.async_set_updated_data(data)

    async def async_start_charging(self) -> None:
        """Start charging."""

        try:
            await self.client.async_start_charging()
        except CommandFailed:
            self.async_set_updated_data(self.client.state)
            raise

    async def async_stop_charging(self) -> None:
        """Stop charging."""

        try:
            await self.client.async_stop_charging()
        except CommandFailed:
            self.async_set_updated_data(self.client.state)
            raise

    async def async_set_charge_amps(self, amps: int) -> None:
        """Set charger amps."""

        await self.client.async_set_charge_amps(amps)

    async def async_set_lcd_brightness(self, brightness: int) -> None:
        """Set LCD brightness."""

        await self.client.async_set_lcd_brightness(brightness)

    async def async_set_temperature_unit(self, unit: str) -> None:
        """Set temperature unit."""

        await self.client.async_set_temperature_unit(unit)

    async def async_set_language(self, language: str) -> None:
        """Set language."""

        await self.client.async_set_language(language)

    async def async_set_device_name(self, name: str) -> None:
        """Set charger name."""

        await self.client.async_set_device_name(name)
