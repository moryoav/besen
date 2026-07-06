"""Base entities for Besen."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import BesenCoordinator


class BesenEntity(CoordinatorEntity[BesenCoordinator]):
    """Base class for Besen entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BesenCoordinator,
        key: str,
        name: str | None = None,
    ) -> None:
        """Initialize the entity."""

        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.address}_{key}"
        if name is None:
            self._attr_translation_key = key
        else:
            self._attr_name = name

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""

        data = self.coordinator.data or self.coordinator.client.state
        info = data.info
        name = data.config.device_name or info.advertised_name or info.model or NAME
        return DeviceInfo(
            identifiers={(DOMAIN, info.address)},
            connections={(dr.CONNECTION_BLUETOOTH, info.address)},
            name=name,
            manufacturer=info.manufacturer or "Besen",
            model=info.model or "BS20",
            serial_number=info.serial,
            hw_version=info.hardware_version,
            sw_version=info.software_version,
        )

    @property
    def available(self) -> bool:
        """Return if the entity is available."""

        data = self.coordinator.data or self.coordinator.client.state
        return data.available and data.authenticated
