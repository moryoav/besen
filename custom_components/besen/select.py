"""Select platform for Besen."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from besen.models import BesenData

from . import BesenConfigEntry
from .const import LANGUAGES, TEMPERATURE_UNITS
from .coordinator import BesenCoordinator
from .entity import BesenEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class BesenSelectEntityDescription(SelectEntityDescription):
    """Besen select description."""

    value_fn: Callable[[BesenData], str | None]
    set_fn: Callable[[BesenCoordinator, str], Awaitable[None]]


SELECTS: tuple[BesenSelectEntityDescription, ...] = (
    BesenSelectEntityDescription(
        key="language",
        name="Language",
        value_fn=lambda data: data.config.language,
        set_fn=lambda coordinator, value: coordinator.async_set_language(value),
        options=list(LANGUAGES),
        icon="mdi:translate",
        entity_category=EntityCategory.CONFIG,
    ),
    BesenSelectEntityDescription(
        key="temperature_unit",
        name="Temperature Unit",
        value_fn=lambda data: data.config.temperature_unit,
        set_fn=lambda coordinator, value: coordinator.async_set_temperature_unit(value),
        options=list(TEMPERATURE_UNITS),
        icon="mdi:thermometer",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BesenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Besen selects."""

    async_add_entities(
        [
            BesenSelect(entry.runtime_data.coordinator, description)
            for description in SELECTS
        ]
    )


class BesenSelect(BesenEntity, SelectEntity):
    """Besen select."""

    entity_description: BesenSelectEntityDescription

    def __init__(
        self,
        coordinator: BesenCoordinator,
        description: BesenSelectEntityDescription,
    ) -> None:
        """Initialize the select."""

        super().__init__(
            coordinator,
            description.key,
            name=cast(str | None, description.name),
        )
        self.entity_description = description
        self._attr_options = list(description.options or [])

    @property
    def current_option(self) -> str | None:
        """Return the selected option."""

        data = self.coordinator.data or self.coordinator.client.state
        return self.entity_description.value_fn(data)

    async def async_select_option(self, option: str) -> None:
        """Select an option."""

        await self.entity_description.set_fn(self.coordinator, option)
