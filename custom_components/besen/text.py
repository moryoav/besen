"""Text platform for Besen."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.const import EntityCategory
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
    """Set up Besen text entities."""

    async_add_entities([BesenNameText(entry.runtime_data.coordinator)])


class BesenNameText(BesenEntity, TextEntity):
    """Charger device name text entity."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min = 1
    _attr_native_max = 11
    _attr_icon = "mdi:rename-outline"

    def __init__(self, coordinator: BesenCoordinator) -> None:
        """Initialize the text entity."""

        super().__init__(coordinator, "device_name", name="Name")

    @property
    def native_value(self) -> str | None:
        """Return charger name."""

        data = self.coordinator.data or self.coordinator.client.state
        return data.config.device_name

    async def async_set_value(self, value: str) -> None:
        """Set charger name."""

        await self.coordinator.async_set_device_name(value)
