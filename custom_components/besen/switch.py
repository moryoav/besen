"""Switch platform for Besen."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BesenConfigEntry
from .coordinator import BesenCoordinator
from .entity import BesenEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BesenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Besen switches."""

    async_add_entities([BesenChargeSwitch(entry.runtime_data.coordinator)])


class BesenChargeSwitch(BesenEntity, SwitchEntity):
    """Charging control switch."""

    _attr_icon = "mdi:ev-plug-type2"

    def __init__(self, coordinator: BesenCoordinator) -> None:
        """Initialize the switch."""

        super().__init__(coordinator, "charging", name="Charge")

    @property
    def is_on(self) -> bool | None:
        """Return whether charging is active."""

        data = self.coordinator.data or self.coordinator.client.state
        return data.charge.charger_status

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start charging."""

        await self.coordinator.async_start_charging()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop charging."""

        await self.coordinator.async_stop_charging()
