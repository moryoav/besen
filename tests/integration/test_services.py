"""Tests for the Besen services."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock

from besen.exceptions import CommandFailed
import probatio
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.besen.const import DOMAIN
from custom_components.besen.services import (
    ATTR_DURATION,
    ATTR_START,
    SERVICE_START_CHARGING,
)

from .conftest import setup_integration

ENTITY_ID = "switch.garage_charge"


@pytest.mark.parametrize(
    ("service_data", "start", "duration_minutes"),
    [
        ({}, None, None),
        (
            {ATTR_START: "2026-10-01T22:00:00+00:00"},
            datetime(2026, 10, 1, 22, 0, tzinfo=UTC),
            None,
        ),
        (
            # A time without an offset is in the Home Assistant time zone.
            {ATTR_START: "2026-10-01 15:00:00"},
            datetime(2026, 10, 1, 22, 0, tzinfo=UTC),
            None,
        ),
        ({ATTR_DURATION: {"hours": 1, "minutes": 30}}, None, 90),
        (
            {
                ATTR_START: "2026-10-01T22:00:00+00:00",
                ATTR_DURATION: {"minutes": 45},
            },
            datetime(2026, 10, 1, 22, 0, tzinfo=UTC),
            45,
        ),
    ],
)
async def test_start_charging(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    service_data: dict[str, Any],
    start: datetime | None,
    duration_minutes: int | None,
) -> None:
    """Test the start charging action passes the schedule to the charger."""

    await setup_integration(hass, mock_config_entry, [Platform.SWITCH])

    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_CHARGING,
        {ATTR_ENTITY_ID: ENTITY_ID, **service_data},
        blocking=True,
    )

    mock_besen_client.async_start_charging.assert_awaited_once_with(
        start=start, duration_minutes=duration_minutes
    )


@pytest.mark.parametrize(
    "duration",
    [{"seconds": 59}, {"minutes": 65535}],
)
async def test_start_charging_invalid_duration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    duration: dict[str, int],
) -> None:
    """Test a duration the charger cannot store is rejected."""

    await setup_integration(hass, mock_config_entry, [Platform.SWITCH])

    with pytest.raises(probatio.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_START_CHARGING,
            {ATTR_ENTITY_ID: ENTITY_ID, ATTR_DURATION: duration},
            blocking=True,
        )

    mock_besen_client.async_start_charging.assert_not_awaited()


@pytest.mark.parametrize(
    ("side_effect", "exception", "translation_key"),
    [
        (ValueError("in the past"), ServiceValidationError, "invalid_start"),
        (CommandFailed("rejected"), HomeAssistantError, "command_failed"),
    ],
)
async def test_start_charging_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    side_effect: Exception,
    exception: type[HomeAssistantError],
    translation_key: str,
) -> None:
    """Test an unusable start time and a charger rejection are reported."""

    mock_besen_client.async_start_charging.side_effect = side_effect

    await setup_integration(hass, mock_config_entry, [Platform.SWITCH])

    with pytest.raises(exception) as err:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_START_CHARGING,
            {ATTR_ENTITY_ID: ENTITY_ID, ATTR_START: "2026-10-01T22:00:00+00:00"},
            blocking=True,
        )

    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == translation_key
