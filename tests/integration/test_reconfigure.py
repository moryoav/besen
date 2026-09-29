"""Tests for Besen PIN reconfiguration."""

from unittest.mock import Mock, patch

from besen.exceptions import CannotConnect, InvalidAuth
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME, CONF_PIN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.besen.const import DOMAIN

from .conftest import (
    FAKE_BLE_DEVICE,
    FIXTURE_ADDRESS,
    FIXTURE_NAME,
    FIXTURE_PIN,
    setup_integration,
)

NEW_PIN = "654321"


async def test_reconfigure_flow(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
) -> None:
    """Test reconfiguration updates the PIN and reloads the entry."""

    await setup_integration(hass, mock_config_entry)
    result = await mock_config_entry.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    mock_besen_client.async_stop.assert_not_awaited()

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PIN: NEW_PIN},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data == {
        CONF_ADDRESS: FIXTURE_ADDRESS,
        CONF_NAME: FIXTURE_NAME,
        CONF_PIN: NEW_PIN,
    }
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    # The running connection is released before the PIN is checked.
    assert mock_besen_client.async_stop.await_count == 2
    assert mock_besen_client.async_start.await_count == 3


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        pytest.param(InvalidAuth("bad pin"), "invalid_auth", id="invalid-auth"),
        pytest.param(CannotConnect("cannot connect"), "cannot_connect", id="connect"),
        pytest.param(RuntimeError("boom"), "unknown", id="unknown"),
    ],
)
async def test_reconfigure_flow_errors_can_recover(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    exception: Exception,
    error: str,
) -> None:
    """Test reconfiguration errors keep the saved PIN and can recover."""

    await setup_integration(hass, mock_config_entry)
    # Check, reconnect with the saved PIN, check again, then reload.
    mock_besen_client.async_start.side_effect = [exception, None, None, None]
    result = await mock_config_entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PIN: NEW_PIN},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": error}
    assert mock_config_entry.data[CONF_PIN] == FIXTURE_PIN
    assert mock_config_entry.state is ConfigEntryState.LOADED

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PIN: NEW_PIN},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_PIN] == NEW_PIN
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_reconfigure_flow_no_connectable_path_can_recover(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    mock_ble_device: Mock,
) -> None:
    """Test reconfiguration recovers after a path becomes available."""

    await setup_integration(hass, mock_config_entry)
    result = await mock_config_entry.start_reconfigure_flow(hass)

    mock_ble_device.return_value = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PIN: NEW_PIN},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "no_connectable_path"}
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY

    mock_ble_device.return_value = FAKE_BLE_DEVICE
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PIN: NEW_PIN},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_PIN] == NEW_PIN
    assert mock_config_entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize(
    ("exception", "error", "state"),
    [
        (CannotConnect("offline"), "cannot_connect", ConfigEntryState.SETUP_RETRY),
        (InvalidAuth("bad pin"), "invalid_auth", ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_reconfigure_flow_entry_not_loaded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    exception: Exception,
    error: str,
    state: ConfigEntryState,
) -> None:
    """Test reconfiguring an entry that failed to set up."""

    mock_besen_client.async_start.side_effect = exception
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is state

    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PIN: NEW_PIN},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert mock_config_entry.state is state

    mock_besen_client.async_start.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PIN: NEW_PIN},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_PIN] == NEW_PIN
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_reconfigure_flow_unload_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
) -> None:
    """Test reconfiguration aborts if the running connection cannot be released."""

    await setup_integration(hass, mock_config_entry)
    result = await mock_config_entry.start_reconfigure_flow(hass)

    with patch.object(hass.config_entries, "async_unload", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PIN: NEW_PIN},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_unload_failed"
    assert mock_config_entry.data[CONF_PIN] == FIXTURE_PIN
    mock_besen_client.async_start.assert_awaited_once()
