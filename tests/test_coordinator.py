"""Tests for the Besen coordinator."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from besen.exceptions import CommandFailed
from besen.models import BesenData, ChargerInfo
from custom_components.besen.coordinator import BesenCoordinator


class _FakeClient:
    """Fake client used by coordinator tests."""

    def __init__(self) -> None:
        """Initialize the fake client."""

        self.state = BesenData(info=ChargerInfo(address="AA:BB"))
        self.calls: list[tuple[str, object | None]] = []
        self.listener: Callable[[BesenData], None] | None = None
        self.removed = False
        self.fail_next_command = False

    def add_listener(
        self,
        listener: Callable[[BesenData], None],
    ) -> Callable[[], None]:
        """Record a listener."""

        self.listener = listener

        def _remove() -> None:
            self.removed = True

        return _remove

    async def async_start(self) -> None:
        """Record start."""

        self.calls.append(("start", None))

    async def async_stop(self) -> None:
        """Record stop."""

        self.calls.append(("stop", None))

    async def async_start_charging(self) -> None:
        """Record start charging."""

        if self.fail_next_command:
            self.fail_next_command = False
            raise CommandFailed("failed")
        self.calls.append(("start_charging", None))

    async def async_stop_charging(self) -> None:
        """Record stop charging."""

        if self.fail_next_command:
            self.fail_next_command = False
            raise CommandFailed("failed")
        self.calls.append(("stop_charging", None))

    async def async_set_charge_amps(self, amps: int) -> None:
        """Record amps."""

        self.calls.append(("charge_amps", amps))

    async def async_set_lcd_brightness(self, brightness: int) -> None:
        """Record brightness."""

        self.calls.append(("lcd_brightness", brightness))

    async def async_set_temperature_unit(self, unit: str) -> None:
        """Record temperature unit."""

        self.calls.append(("temperature_unit", unit))

    async def async_set_language(self, language: str) -> None:
        """Record language."""

        self.calls.append(("language", language))

    async def async_set_device_name(self, name: str) -> None:
        """Record name."""

        self.calls.append(("device_name", name))


def _patch_coordinator_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch DataUpdateCoordinator init for direct unit testing."""

    def _init(
        self: object,
        hass: object,
        logger: logging.Logger,
        *,
        name: str,
        update_method: Callable[[], Awaitable[BesenData]],
    ) -> None:
        del hass, logger, name
        cast(Any, self).data = None
        cast(Any, self).update_method = update_method

        def _set_updated_data(data: BesenData) -> None:
            cast(Any, self).data = data

        cast(Any, self).async_set_updated_data = _set_updated_data

    monkeypatch.setattr(
        DataUpdateCoordinator,
        "__init__",
        _init,
    )


@pytest.mark.asyncio
async def test_coordinator_lifecycle_and_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coordinator starts, handles updates, and shuts down."""

    _patch_coordinator_base(monkeypatch)
    client = _FakeClient()
    coordinator = BesenCoordinator(cast(Any, SimpleNamespace()), cast(Any, client))

    await coordinator.async_start()
    new_state = BesenData(
        info=ChargerInfo(address="AA:BB", model="BS20"),
        available=True,
    )
    assert client.listener is not None
    client.listener(new_state)
    update = await coordinator._async_update_data()
    await coordinator.async_shutdown()

    assert coordinator.data == new_state
    assert update == client.state
    assert client.removed is True
    assert client.calls == [("start", None), ("stop", None)]


@pytest.mark.asyncio
async def test_coordinator_commands_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coordinator delegates commands and refreshes state on command failures."""

    _patch_coordinator_base(monkeypatch)
    client = _FakeClient()
    coordinator = BesenCoordinator(cast(Any, SimpleNamespace()), cast(Any, client))

    await coordinator.async_start_charging()
    await coordinator.async_stop_charging()
    await coordinator.async_set_charge_amps(12)
    await coordinator.async_set_lcd_brightness(80)
    await coordinator.async_set_temperature_unit("Fahrenheit")
    await coordinator.async_set_language("Deutsch")
    await coordinator.async_set_device_name("Garage")

    assert client.calls == [
        ("start_charging", None),
        ("stop_charging", None),
        ("charge_amps", 12),
        ("lcd_brightness", 80),
        ("temperature_unit", "Fahrenheit"),
        ("language", "Deutsch"),
        ("device_name", "Garage"),
    ]

    client.fail_next_command = True
    with pytest.raises(CommandFailed):
        await coordinator.async_start_charging()
    assert coordinator.data == client.state

    client.fail_next_command = True
    with pytest.raises(CommandFailed):
        await coordinator.async_stop_charging()
    assert coordinator.data == client.state
