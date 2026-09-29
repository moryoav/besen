"""Tests for Besen PIN reconfiguration."""

from asyncio import CancelledError
from collections.abc import Generator
import json
from unittest.mock import AsyncMock, Mock, call, patch

from besen.exceptions import CannotConnect, InvalidAuth
from probatio import to_field_list
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME, CONF_PIN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)

from custom_components.besen.const import DOMAIN

from .conftest import (
    FAKE_BLE_DEVICE,
    FIXTURE_ADDRESS,
    FIXTURE_NAME,
    FIXTURE_PIN,
    charger_state,
    setup_integration,
)

NEW_PIN = "654321"


@pytest.fixture
def mock_validation_client(mock_besen_client: Mock) -> Generator[Mock]:
    """Use a separate client for PIN validation and the running integration."""

    client = Mock(
        state=charger_state(),
        async_start=AsyncMock(),
        async_stop=AsyncMock(),
    )
    with patch(
        "custom_components.besen.config_flow.BesenClient", return_value=client
    ) as factory:
        yield factory


async def test_reconfigure_form(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    mock_validation_client: Mock,
) -> None:
    """Opening or closing the PIN form must not disconnect the charger."""

    await setup_integration(hass, mock_config_entry)
    result = await mock_config_entry.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    fields = to_field_list(
        result["data_schema"], custom_serializer=cv.custom_serializer
    )
    assert len(fields) == 1
    assert fields[0]["name"] == CONF_PIN
    assert fields[0]["required"] is True
    assert fields[0]["selector"]["text"]["type"] == "password"
    assert "default" not in fields[0]
    assert FIXTURE_PIN not in json.dumps(fields)

    hass.config_entries.flow.async_abort(result["flow_id"])
    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_validation_client.assert_not_called()
    mock_besen_client.async_stop.assert_not_awaited()


@pytest.mark.parametrize("pin", [NEW_PIN, FIXTURE_PIN, "012345"])
async def test_reconfigure_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    mock_validation_client: Mock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    pin: str,
) -> None:
    """Reload with the PIN while keeping the entry, devices and entities."""

    await setup_integration(hass, mock_config_entry)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, "other_data": "keep"},
        options={"other_option": True},
    )
    original_data = dict(mock_config_entry.data)
    original_title = mock_config_entry.title
    original_unique_id = mock_config_entry.unique_id
    entity_ids = {
        entity.id
        for entity in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
    }
    device_ids = {
        device.id
        for device in dr.async_entries_for_config_entry(
            device_registry, mock_config_entry.entry_id
        )
    }
    assert entity_ids
    assert device_ids
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="CC:DD",
        data={CONF_ADDRESS: "CC:DD", CONF_PIN: "111111"},
    )
    other_entry.add_to_hass(hass)

    order = Mock()
    order.attach_mock(mock_besen_client.async_stop, "disconnect")
    order.attach_mock(mock_validation_client.return_value.async_start, "validate")
    order.attach_mock(mock_validation_client.return_value.async_stop, "cleanup")
    order.attach_mock(mock_besen_client.async_start, "reconnect")

    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: pin}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert order.mock_calls == [
        call.disconnect(),
        call.validate(),
        call.cleanup(),
        call.reconnect(),
    ]
    kwargs = mock_validation_client.call_args.kwargs
    assert kwargs["address"] == FIXTURE_ADDRESS
    assert kwargs["advertised_name"] == FIXTURE_NAME
    assert kwargs["pin"] == pin
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert (
        hass.config_entries.async_get_entry(mock_config_entry.entry_id)
        is mock_config_entry
    )
    assert mock_config_entry.data == {**original_data, CONF_PIN: pin}
    assert mock_config_entry.data[CONF_NAME] == FIXTURE_NAME
    assert mock_config_entry.options == {"other_option": True}
    assert mock_config_entry.title == original_title
    assert mock_config_entry.unique_id == original_unique_id
    assert hass.config_entries.async_entries(DOMAIN) == [mock_config_entry, other_entry]
    assert other_entry.data == {CONF_ADDRESS: "CC:DD", CONF_PIN: "111111"}
    assert {
        entity.id
        for entity in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
    } == entity_ids
    assert {
        device.id
        for device in dr.async_entries_for_config_entry(
            device_registry, mock_config_entry.entry_id
        )
    } == device_ids
    mock_besen_client.async_start_charging.assert_not_awaited()
    mock_besen_client.async_stop_charging.assert_not_awaited()


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (InvalidAuth("bad pin"), "invalid_auth"),
        (CannotConnect("offline"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_reconfigure_errors_can_recover(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    mock_validation_client: Mock,
    exception: Exception,
    error: str,
) -> None:
    """Failed validation restores the old connection and allows another attempt."""

    await setup_integration(hass, mock_config_entry)
    original_data = dict(mock_config_entry.data)
    probe = mock_validation_client.return_value
    probe.async_start.side_effect = [exception, None]
    result = await mock_config_entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: NEW_PIN}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": error}
    assert mock_config_entry.data == original_data
    assert mock_config_entry.state is ConfigEntryState.LOADED
    probe.async_stop.assert_awaited_once()
    assert mock_besen_client.async_start.await_count == 2
    fields = to_field_list(
        result["data_schema"], custom_serializer=cv.custom_serializer
    )
    assert NEW_PIN not in json.dumps(fields)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: NEW_PIN}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_PIN] == NEW_PIN
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert probe.async_stop.await_count == 2


@pytest.mark.parametrize(
    "pin",
    [
        "12345",
        "1234567",
        "abcdef",
        "¹²³⁴⁵⁶",
        pytest.param("٠١٢٣٤٥", id="arabic-indic-digits"),
        pytest.param("\uff10\uff11\uff12\uff13\uff14\uff15", id="fullwidth-digits"),
        "",
    ],
)
async def test_reconfigure_invalid_pin(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    mock_validation_client: Mock,
    pin: str,
) -> None:
    """Reject malformed PINs before disconnecting or contacting the charger."""

    await setup_integration(hass, mock_config_entry)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: pin}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert mock_config_entry.data[CONF_PIN] == FIXTURE_PIN
    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_besen_client.async_stop.assert_not_awaited()
    mock_validation_client.assert_not_called()


async def test_reconfigure_without_connectable_path(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_validation_client: Mock,
    mock_ble_device: Mock,
) -> None:
    """A missing Bluetooth path keeps the old PIN and can recover on retry."""

    await setup_integration(hass, mock_config_entry)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    mock_ble_device.return_value = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: NEW_PIN}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_connectable_path"}
    assert mock_config_entry.data[CONF_PIN] == FIXTURE_PIN
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_validation_client.assert_not_called()

    mock_ble_device.return_value = FAKE_BLE_DEVICE
    with patch.object(
        mock_config_entry,
        "async_cancel_retry_setup",
        wraps=mock_config_entry.async_cancel_retry_setup,
    ) as cancel_retry:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PIN: NEW_PIN}
        )
        cancel_retry.assert_called()
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_PIN] == NEW_PIN
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_reconfigure_before_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_validation_client: Mock,
) -> None:
    """Reconfigure an entry that has not loaded without requiring runtime data."""

    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: NEW_PIN}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_PIN] == NEW_PIN
    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_validation_client.return_value.async_stop.assert_awaited_once()


async def test_reconfigure_unload_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_validation_client: Mock,
) -> None:
    """Do not probe if the existing connection cannot close."""

    await setup_integration(hass, mock_config_entry)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    with patch.object(hass.config_entries, "async_unload", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PIN: NEW_PIN}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_unload_failed"
    assert mock_config_entry.data[CONF_PIN] == FIXTURE_PIN
    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_validation_client.assert_not_called()


async def test_reconfigure_cancelled_validation(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_validation_client: Mock,
) -> None:
    """Close the probe and restore the connection after cancellation."""

    await setup_integration(hass, mock_config_entry)
    probe = mock_validation_client.return_value
    probe.async_start.side_effect = CancelledError
    result = await mock_config_entry.start_reconfigure_flow(hass)

    with pytest.raises(CancelledError):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PIN: NEW_PIN}
        )
    await hass.async_block_till_done()

    assert mock_config_entry.data[CONF_PIN] == FIXTURE_PIN
    assert mock_config_entry.state is ConfigEntryState.LOADED
    probe.async_stop.assert_awaited_once()
