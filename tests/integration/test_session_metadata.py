"""Visible session reasons, reported identities and diagnostic privacy."""

from datetime import UTC, datetime, timedelta
import json
from unittest.mock import Mock

from besen.const import STOP_REASON
from besen.models import ChargeStatus, SessionRecord
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.besen.diagnostics import async_get_config_entry_diagnostics
from custom_components.besen.sensor import SESSION_STOP_REASONS

from . import publish_besen_state
from .conftest import charger_state, setup_integration

REASON_ENTITY = "sensor.garage_last_session_stop_reason"
START_ENTITY = "sensor.garage_session_start"
STARTED = datetime(2026, 10, 25, 12, 0, 2, tzinfo=UTC)
ENDED = STARTED + timedelta(seconds=6)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (11, "stopped_by_software"),
        (13, "vehicle_finished"),
        (17, "cable_unplugged"),
        (24, "stopped_by_button"),
        (99, "unrecognized"),
    ],
)
async def test_visible_stop_reason(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    entity_registry: er.EntityRegistry,
    code: int,
    expected: str,
) -> None:
    """A normally enabled sensor exposes the raw code and observed record."""

    await setup_integration(hass, mock_config_entry, [Platform.SENSOR])
    assert (entry := entity_registry.async_get(REASON_ENTITY)) is not None
    assert entry.disabled_by is None
    assert (state := hass.states.get(REASON_ENTITY)) is not None
    assert state.state == STATE_UNKNOWN
    assert "session_id" not in state.attributes

    record = SessionRecord(
        session_id="shared-minute-id",
        started_by="client-A",
        stopped_by="Key",
        started_at=STARTED,
        ended_at=ENDED,
        stop_reason_code=code,
    )
    publish_besen_state(mock_besen_client, charger_state().updated(last_session=record))
    await hass.async_block_till_done()
    assert (state := hass.states.get(REASON_ENTITY)) is not None
    assert state.state == expected
    assert state.attributes["session_id"] == "shared-minute-id"
    assert state.attributes["started_by"] == "client-A"
    assert state.attributes["stopped_by"] == "Key"
    assert state.attributes["stop_reason_code"] == code
    assert state.attributes["started_at"] == STARTED.isoformat()
    assert state.attributes["ended_at"] == ENDED.isoformat()

    # A new session with the same ID and reason must still update the attributes.
    later = SessionRecord(
        session_id="shared-minute-id",
        started_by="client-A",
        stopped_by="Key",
        started_at=STARTED + timedelta(seconds=20),
        ended_at=ENDED + timedelta(seconds=20),
        stop_reason_code=code,
    )
    publish_besen_state(mock_besen_client, charger_state().updated(last_session=later))
    await hass.async_block_till_done()
    assert (later_state := hass.states.get(REASON_ENTITY)) is not None
    assert later_state.state == expected
    assert later_state.attributes["ended_at"] != state.attributes["ended_at"]
    assert entity_registry.async_get(REASON_ENTITY) is entry


async def test_active_and_last_session_are_independent(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
) -> None:
    """Current ownership clears with its report while the last end stays cached."""

    await setup_integration(hass, mock_config_entry, [Platform.SENSOR])
    previous = SessionRecord(stop_reason_code=24, started_by="previous-client")
    current = charger_state(
        charge=ChargeStatus(
            session_start=STARTED, session_id="current-id", session_started_by="Key"
        )
    ).updated(last_session=previous)
    publish_besen_state(mock_besen_client, current)
    await hass.async_block_till_done()
    assert (state := hass.states.get(START_ENTITY)) is not None
    assert state.attributes["session_id"] == "current-id"
    assert state.attributes["started_by"] == "Key"
    assert (reason := hass.states.get(REASON_ENTITY)) is not None
    assert reason.attributes["started_by"] == "previous-client"
    assert reason.attributes["ended_at"] is None

    publish_besen_state(mock_besen_client, current.updated(charge=ChargeStatus()))
    await hass.async_block_till_done()
    assert (state := hass.states.get(START_ENTITY)) is not None
    assert state.state == STATE_UNKNOWN
    assert state.attributes["session_id"] is None
    assert state.attributes["started_by"] is None
    assert hass.states.get(REASON_ENTITY) == reason

    publish_besen_state(mock_besen_client, current.updated(available=False))
    await hass.async_block_till_done()
    assert (state := hass.states.get(REASON_ENTITY)) is not None
    assert state.state == STATE_UNAVAILABLE
    publish_besen_state(mock_besen_client, current)
    await hass.async_block_till_done()
    assert (state := hass.states.get(REASON_ENTITY)) is not None
    assert state.state == "stopped_by_button"


async def test_missing_reason_is_unknown(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
) -> None:
    """An incomplete model does not invent a reason or a time."""

    mock_besen_client.state = charger_state().updated(last_session=SessionRecord())
    await setup_integration(hass, mock_config_entry, [Platform.SENSOR])
    assert (state := hass.states.get(REASON_ENTITY)) is not None
    assert state.state == STATE_UNKNOWN
    assert state.attributes["stop_reason_code"] is None


async def test_session_diagnostics_redact_all_identifiers(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
) -> None:
    """A diagnostic download includes reasons and times but no participant IDs."""

    state = charger_state(
        charge=ChargeStatus(
            session_id="private-current-session", session_started_by="private-phone-A"
        )
    ).updated(
        last_session=SessionRecord(
            session_id="private-old-session",
            started_by="private-phone-B",
            stopped_by="private-card-C",
            started_at=STARTED,
            ended_at=ENDED,
            stop_reason_code=11,
            stop_reason="App stop",
        )
    )
    mock_besen_client.state = state
    await setup_integration(hass, mock_config_entry, [Platform.SENSOR])
    before = list(mock_besen_client.mock_calls)
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    serialized = json.dumps(result, default=str)
    assert "private-" not in serialized
    assert result["data"]["last_session"]["stop_reason_code"] == 11
    assert result["data"]["last_session"]["ended_at"] == ENDED
    assert mock_besen_client.mock_calls == before
    assert mock_besen_client.state is state
    assert state.charge.session_started_by == "private-phone-A"


def test_known_stop_reasons_have_stable_options() -> None:
    """Known library reasons do not silently become unrecognized in HA."""

    assert SESSION_STOP_REASONS.keys() == STOP_REASON.keys()
