"""Tests for the additional session and reservation sensor entities."""

from datetime import UTC, datetime
from unittest.mock import Mock

from besen.models import ChargeStatus
from besen.protocol import PARSERS
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import publish_besen_state
from .conftest import charger_state, setup_integration

SESSION_KEYS = (
    "session_start",
    "session_duration",
    "session_current_limit",
    "reservation_start",
    "reservation_duration",
)


@pytest.mark.parametrize("phases", [1, 3])
@pytest.mark.parametrize(
    ("key", "device_class", "unit"),
    [
        ("session_start", "timestamp", None),
        ("session_duration", "duration", "s"),
        ("session_current_limit", "current", "A"),
        ("reservation_start", "timestamp", None),
        ("reservation_duration", "duration", "min"),
    ],
)
async def test_session_entity_registration(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    phases: int,
    key: str,
    device_class: str,
    unit: str | None,
) -> None:
    """Each new entity exists by default, with stable IDs and correct metadata."""
    mock_besen_client.state = charger_state(phases=phases)
    await setup_integration(hass, mock_config_entry, [Platform.SENSOR])
    entity_id = f"sensor.garage_{key}"
    assert (entry := entity_registry.async_get(entity_id)) is not None
    assert entry.unique_id == f"{mock_besen_client.address}_{key}"
    assert entry.translation_key == key
    assert entry.disabled_by is None
    assert entry.entity_category is None
    assert (state := hass.states.get(entity_id)) is not None
    assert state.state == STATE_UNKNOWN
    assert state.attributes[ATTR_DEVICE_CLASS] == device_class
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == unit


@pytest.mark.parametrize("command", [5, 6])
async def test_session_report_updates_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    command: int,
) -> None:
    """Live and completed reports reach HA with timestamps, seconds and minutes."""
    await setup_integration(hass, mock_config_entry, [Platform.SENSOR])
    payload = bytearray(74)
    payload[20:22] = (180).to_bytes(2, "big")
    payload[26:30] = (1_789_747_200).to_bytes(4, "big")
    payload[46] = 16
    payload[47:51] = (1_789_750_800).to_bytes(4, "big")
    payload[51:55] = (3661).to_bytes(4, "big")
    payload[63:67] = (456).to_bytes(4, "big")
    charge = ChargeStatus(**PARSERS[command](bytes(payload), ""))
    publish_besen_state(
        mock_besen_client, charger_state(charge=charge, charge_amps=32)
    )
    await hass.async_block_till_done()
    assert charge.session_start is not None
    assert charge.reservation_start is not None
    expected = {
        "session_start": charge.session_start.isoformat(),
        "session_duration": "3661",
        "session_current_limit": "16",
        "reservation_start": charge.reservation_start.isoformat(),
        "reservation_duration": "180",
        "session_energy": "4.56",
    }
    for key, value in expected.items():
        assert (state := hass.states.get(f"sensor.garage_{key}")) is not None
        assert state.state == value

    # An empty new report must clear stale dates/limits, while preserving zero.
    publish_besen_state(
        mock_besen_client,
        charger_state(charge=charge.updated(**PARSERS[command](bytes(74), ""))),
    )
    await hass.async_block_till_done()
    for key in SESSION_KEYS:
        assert (state := hass.states.get(f"sensor.garage_{key}")) is not None
        assert state.state == ("0" if key == "session_duration" else STATE_UNKNOWN)


@pytest.mark.parametrize(
    ("available", "authenticated"), [(False, True), (True, False)]
)
async def test_session_entities_disconnect_and_recover(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    available: bool,
    authenticated: bool,
) -> None:
    """All five sensors follow connection/authentication and recover with data."""
    charge = ChargeStatus(
        session_start=datetime(2026, 9, 18, 12, tzinfo=UTC),
        session_duration=60,
        session_current_limit=16,
        reservation_start=datetime(2026, 9, 18, 11, tzinfo=UTC),
        reservation_duration=180,
    )
    mock_besen_client.state = charger_state(charge=charge)
    await setup_integration(hass, mock_config_entry, [Platform.SENSOR])
    publish_besen_state(
        mock_besen_client,
        charger_state(
            charge=charge, available=available, authenticated=authenticated
        ),
    )
    await hass.async_block_till_done()
    for key in SESSION_KEYS:
        assert (state := hass.states.get(f"sensor.garage_{key}")) is not None
        assert state.state == STATE_UNAVAILABLE
    publish_besen_state(mock_besen_client, charger_state(charge=charge))
    await hass.async_block_till_done()
    for key in SESSION_KEYS:
        assert (state := hass.states.get(f"sensor.garage_{key}")) is not None
        assert state.state not in {STATE_UNKNOWN, STATE_UNAVAILABLE}
