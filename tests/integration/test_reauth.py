"""Tests for Besen PIN reauthentication and runtime authentication failures."""

from unittest.mock import Mock, patch

from besen.exceptions import CannotConnect, InvalidAuth, NoConnectablePath
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME, CONF_PIN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.besen.const import DOMAIN

from . import publish_besen_state
from .conftest import (
    FIXTURE_ADDRESS,
    FIXTURE_NAME,
    FIXTURE_PIN,
    charger_state,
    setup_integration,
)


@pytest.mark.parametrize("pin", ["654321", FIXTURE_PIN])
async def test_reauth_updates_only_pin(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    pin: str,
) -> None:
    """Validate the stored charger and reload even when the PIN is unchanged."""

    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, "preserved_data": "value"},
        options={"preserved_option": True},
    )
    original_data = dict(mock_config_entry.data)
    original_options = dict(mock_config_entry.options)
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="CC:DD",
        title="Other charger",
        data={CONF_ADDRESS: "CC:DD", CONF_NAME: "Other", CONF_PIN: "111111"},
    )
    other_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
            "unique_id": mock_config_entry.unique_id,
        },
        data=mock_config_entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert not result["errors"]
    mock_besen_client.async_start.assert_not_awaited()

    with (
        patch.object(hass.config_entries, "async_reload", return_value=True) as reload,
        patch(
            "custom_components.besen.config_flow.BesenClient",
            return_value=mock_besen_client,
        ) as factory,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PIN: pin}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data == {**original_data, CONF_PIN: pin}
    assert mock_config_entry.options == original_options
    assert mock_config_entry.title == "Garage"
    assert mock_config_entry.unique_id == FIXTURE_ADDRESS
    assert other_entry.data[CONF_PIN] == "111111"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2
    reload.assert_awaited_once_with(mock_config_entry.entry_id)
    mock_besen_client.async_start.assert_awaited_once()
    mock_besen_client.async_stop.assert_awaited_once()
    assert factory.call_args.kwargs["address"] == FIXTURE_ADDRESS
    assert factory.call_args.kwargs["advertised_name"] == FIXTURE_NAME
    assert factory.call_args.kwargs["pin"] == pin


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (InvalidAuth("Rejected"), "invalid_auth"),
        (NoConnectablePath("No path"), "no_connectable_path"),
        (CannotConnect("Offline"), "cannot_connect"),
        (RuntimeError("Unexpected"), "unknown"),
    ],
)
async def test_reauth_validation_error_and_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    exception: Exception,
    error: str,
) -> None:
    """Failed validation retains the original credentials and allows a retry."""

    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=mock_config_entry.data,
    )
    mock_besen_client.async_start.side_effect = exception
    with patch.object(hass.config_entries, "async_reload", return_value=True) as reload:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PIN: "654321"}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"
        assert result["errors"] == {"base": error}
        assert mock_config_entry.data[CONF_PIN] == FIXTURE_PIN
        reload.assert_not_awaited()
        mock_besen_client.async_stop.assert_awaited_once()
        mock_besen_client.async_start.side_effect = None
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PIN: "654321"}
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PIN] == "654321"
    reload.assert_awaited_once_with(mock_config_entry.entry_id)


@pytest.mark.parametrize("pin", ["", "12345", "1234567", "abcdef"])
async def test_reauth_rejects_malformed_pin(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    pin: str,
) -> None:
    """Malformed PINs are rejected before opening a Bluetooth connection."""

    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=mock_config_entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: pin}
    )
    assert result["errors"] == {"base": "invalid_auth"}
    assert mock_config_entry.data[CONF_PIN] == FIXTURE_PIN
    mock_besen_client.async_start.assert_not_awaited()


async def test_reauth_without_connectable_path(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    mock_ble_device: Mock,
) -> None:
    """An absent proxy is reported as connectivity, not a rejected PIN."""

    mock_config_entry.add_to_hass(hass)
    mock_ble_device.return_value = None
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=mock_config_entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: "654321"}
    )
    assert result["errors"] == {"base": "no_connectable_path"}
    assert mock_config_entry.data[CONF_PIN] == FIXTURE_PIN
    mock_besen_client.async_start.assert_not_awaited()


async def test_setup_auth_failure_starts_one_reauth_flow(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
) -> None:
    """The framework handles startup InvalidAuth, including its state callback."""

    async def reject_login() -> None:
        publish_besen_state(
            mock_besen_client,
            charger_state(available=False, authenticated=False).updated(
                auth_failed=True
            ),
        )
        raise InvalidAuth("Rejected")

    mock_besen_client.async_start.side_effect = reject_login
    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == config_entries.SOURCE_REAUTH
    assert flows[0]["context"]["entry_id"] == mock_config_entry.entry_id
    mock_besen_client.async_stop.assert_awaited_once()


@pytest.mark.parametrize(
    ("available", "authenticated"), [(False, False), (True, False), (True, True)]
)
async def test_runtime_transport_states_do_not_start_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    available: bool,
    authenticated: bool,
) -> None:
    """Only the typed rejection flag starts reauthentication, never error text."""

    await setup_integration(hass, mock_config_entry)
    publish_besen_state(
        mock_besen_client,
        charger_state(available=available, authenticated=authenticated).updated(
            last_error="The charger rejected the configured PIN"
        ),
    )
    await hass.async_block_till_done()
    assert not hass.config_entries.flow.async_progress()


async def test_runtime_reauth_preserves_entities_after_reload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
) -> None:
    """Runtime rejection starts one flow and a validated PIN preserves identities."""

    await setup_integration(hass, mock_config_entry)
    registry = er.async_get(hass)
    before = {
        (entity.id, entity.entity_id, entity.unique_id, entity.device_id)
        for entity in er.async_entries_for_config_entry(
            registry, mock_config_entry.entry_id
        )
    }
    assert before
    rejected = charger_state(available=False, authenticated=False).updated(
        auth_failed=True
    )
    for _ in range(3):
        publish_besen_state(mock_besen_client, rejected)
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == config_entries.SOURCE_REAUTH
    assert flows[0]["context"]["entry_id"] == mock_config_entry.entry_id
    mock_besen_client.state = charger_state()
    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {CONF_PIN: "654321"}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.data[CONF_PIN] == "654321"
    assert mock_config_entry.unique_id == FIXTURE_ADDRESS
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert not hass.config_entries.flow.async_progress()
    after = {
        (entity.id, entity.entity_id, entity.unique_id, entity.device_id)
        for entity in er.async_entries_for_config_entry(
            registry, mock_config_entry.entry_id
        )
    }
    assert before == after


async def test_runtime_reauth_can_start_again_after_recovery(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
) -> None:
    """A later, independent rejection is not hidden by the duplicate guard."""

    await setup_integration(hass, mock_config_entry)
    rejected = charger_state(available=False, authenticated=False).updated(
        auth_failed=True
    )
    publish_besen_state(mock_besen_client, rejected)
    await hass.async_block_till_done()
    first_flow = hass.config_entries.flow.async_progress()[0]
    hass.config_entries.flow.async_abort(first_flow["flow_id"])
    publish_besen_state(mock_besen_client, charger_state())
    publish_besen_state(mock_besen_client, rejected)
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["flow_id"] != first_flow["flow_id"]
