"""LAN setup, transport selection and shared listener regression coverage."""

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, Mock, patch

from besen.exceptions import CannotConnect, InvalidAuth
from besen.udp import BesenUdpClient
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigEntryState,
)
from homeassistant.const import CONF_ADDRESS, CONF_HOST, CONF_NAME, CONF_PIN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.besen.config_flow import BesenConfigFlow
from custom_components.besen.const import CONF_SERIAL, CONF_TRANSPORT, DOMAIN
from custom_components.besen.diagnostics import async_get_config_entry_diagnostics
from custom_components.besen.lan import async_acquire_udp_hub, async_release_udp_hub

from . import publish_besen_state
from .conftest import (
    FIXTURE_ADDRESS,
    FIXTURE_PIN,
    _configure_client_mock,
    charger_state,
)

SERIAL = "8949281891483449"
HOST = "192.0.2.10"


@pytest.fixture(autouse=True)
def hub() -> Generator[Mock]:
    """Keep setup tests independent of the host's network."""
    hub = Mock(async_start=AsyncMock(), async_stop=AsyncMock())
    with patch("custom_components.besen.lan.BesenUdpHub", return_value=hub):
        yield hub


@pytest.fixture
def udp_client() -> Generator[Mock]:
    client = Mock(spec=BesenUdpClient)
    _configure_client_mock(client)
    client.state = charger_state().updated(
        info=charger_state().info.updated(serial=SERIAL)
    )
    client.is_connected = False
    client.host = HOST
    client.async_wait_for_status = AsyncMock()
    client.async_wait_for_heartbeat = AsyncMock()
    with (
        patch("custom_components.besen.BesenUdpClient", return_value=client),
        patch(
            "custom_components.besen.config_flow.BesenUdpClient", return_value=client
        ),
    ):
        yield client


def flow_for(
    hass: HomeAssistant, entry: MockConfigEntry | None = None
) -> BesenConfigFlow:
    flow = BesenConfigFlow()
    flow.hass = hass
    flow.context = {"source": SOURCE_USER}
    if entry:
        entry.add_to_hass(hass)
        flow.context = {"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
        flow._pending_data = dict(entry.data)
        flow._pending_data[CONF_SERIAL] = SERIAL
    return flow


async def test_reconfigure_offers_only_connection_selection(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": mock_config_entry.entry_id},
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["lan", "use_bluetooth"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "lan"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "lan"


async def test_lan_switch_preserves_entry_and_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    udp_client: Mock,
) -> None:
    mock_besen_client.is_connected = False
    mock_besen_client.state = udp_client.state
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    before = {
        entry.entity_id: (entry.unique_id, entry.device_id)
        for entry in er.async_entries_for_config_entry(
            registry, mock_config_entry.entry_id
        )
    }
    flow = BesenConfigFlow()
    flow.hass = hass
    flow.context = {
        "source": SOURCE_RECONFIGURE,
        "entry_id": mock_config_entry.entry_id,
    }
    await flow.async_step_reconfigure()
    result = await flow.async_step_lan({CONF_HOST: HOST, CONF_PIN: FIXTURE_PIN})
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    await flow._operation_task
    udp_client.async_wait_for_status.assert_awaited_once_with(timeout=10)
    udp_client.async_wait_for_heartbeat.assert_awaited_once()
    assert (await flow.async_step_connect())[
        "type"
    ] is FlowResultType.SHOW_PROGRESS_DONE
    result = await flow.async_step_connection_done()
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.unique_id == FIXTURE_ADDRESS
    assert mock_config_entry.data[CONF_ADDRESS] == FIXTURE_ADDRESS
    assert mock_config_entry.data[CONF_TRANSPORT] == "lan"
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert before == {
        entry.entity_id: (entry.unique_id, entry.device_id)
        for entry in er.async_entries_for_config_entry(
            registry, mock_config_entry.entry_id
        )
    }


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (CannotConnect("offline"), "cannot_connect"),
        (InvalidAuth("rejected"), "invalid_auth"),
        (TimeoutError(), "cannot_connect"),
        (RuntimeError("private-pin"), "unknown"),
    ],
)
async def test_failed_lan_validation_restores_connection(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    udp_client: Mock,
    error: Exception,
    expected: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mock_besen_client.is_connected = False
    mock_config_entry.runtime_data = Mock(client=mock_besen_client)
    flow = flow_for(hass, mock_config_entry)
    original = dict(mock_config_entry.data)
    udp_client.async_start.side_effect = error
    await flow.async_step_lan({CONF_HOST: HOST, CONF_PIN: FIXTURE_PIN})
    await flow._operation_task
    result = await flow.async_step_connection_done()
    assert result["errors"] == {"base": expected}
    assert mock_config_entry.data == original
    mock_besen_client.async_start.assert_awaited_once()
    udp_client.async_stop.assert_awaited_once()
    assert "private-pin" not in caplog.text


async def test_cancel_reconfigure_restores_original_transport(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    udp_client: Mock,
) -> None:
    mock_besen_client.is_connected = False
    mock_config_entry.runtime_data = Mock(client=mock_besen_client)
    flow = flow_for(hass, mock_config_entry)
    started = asyncio.Event()

    async def connect() -> None:
        started.set()
        await asyncio.Event().wait()

    udp_client.async_start.side_effect = connect
    await flow.async_step_lan({CONF_HOST: HOST, CONF_PIN: FIXTURE_PIN})
    await started.wait()
    flow.async_remove()
    with pytest.raises(asyncio.CancelledError):
        await flow._operation_task
    mock_besen_client.async_start.assert_awaited_once()
    udp_client.async_stop.assert_awaited_once()
    assert CONF_TRANSPORT not in mock_config_entry.data


@pytest.mark.parametrize("pin", ["12345", "\uff11\uff12\uff13\uff14\uff15\uff16"])
async def test_invalid_lan_pin_never_connects(
    hass: HomeAssistant, udp_client: Mock, pin: str
) -> None:
    flow = flow_for(hass)
    result = await flow.async_step_lan({CONF_HOST: HOST, CONF_PIN: pin})
    assert result["errors"] == {"base": "invalid_auth"}
    udp_client.async_start.assert_not_awaited()


async def test_empty_lan_host_never_connects(
    hass: HomeAssistant, udp_client: Mock
) -> None:
    flow = flow_for(hass)
    result = await flow.async_step_lan({CONF_HOST: "  ", CONF_PIN: FIXTURE_PIN})
    assert result["errors"] == {"base": "cannot_connect"}
    udp_client.async_start.assert_not_awaited()


@pytest.mark.usefixtures("mock_setup_entry")
async def test_new_lan_entry_uses_serial_identity(
    hass: HomeAssistant, udp_client: Mock
) -> None:
    flow = flow_for(hass)
    await flow.async_step_user({CONF_HOST: HOST, CONF_PIN: FIXTURE_PIN})
    await flow._operation_task
    result = await flow.async_step_connection_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert flow.unique_id == f"lan:{SERIAL}"
    assert result["data"] == {
        CONF_HOST: HOST,
        CONF_PIN: FIXTURE_PIN,
        CONF_SERIAL: SERIAL,
        CONF_ADDRESS: f"lan:{SERIAL}",
        CONF_NAME: "BS20",
        CONF_TRANSPORT: "lan",
    }


async def test_duplicate_lan_serial_is_rejected(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, udp_client: Mock
) -> None:
    mock_config_entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=mock_config_entry.entry_id, identifiers={(DOMAIN, SERIAL)}
    )
    flow = flow_for(hass)
    await flow.async_step_lan({CONF_HOST: HOST, CONF_PIN: FIXTURE_PIN})
    await flow._operation_task
    result = await flow.async_step_connection_done()
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_no_identity_cannot_be_saved(
    hass: HomeAssistant, udp_client: Mock
) -> None:
    udp_client.state = udp_client.state.updated(
        info=udp_client.state.info.updated(serial=None)
    )
    flow = flow_for(hass)
    await flow.async_step_lan({CONF_HOST: HOST, CONF_PIN: FIXTURE_PIN})
    await flow._operation_task
    assert (await flow.async_step_connection_done())["errors"] == {
        "base": "cannot_connect"
    }


async def test_lan_only_entry_does_not_offer_unknown_bluetooth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    flow = flow_for(hass, mock_config_entry)
    flow._pending_data[CONF_ADDRESS] = f"lan:{SERIAL}"
    assert (await flow.async_step_use_bluetooth())[
        "reason"
    ] == "bluetooth_address_unknown"


async def test_bluetooth_switch_validates_before_saving(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_besen_client: Mock
) -> None:
    flow = flow_for(hass, mock_config_entry)
    assert (await flow.async_step_use_bluetooth())["type"] is FlowResultType.FORM
    await flow.async_step_use_bluetooth({CONF_PIN: FIXTURE_PIN})
    await flow._operation_task
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()):
        result = await flow.async_step_connection_done()
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_TRANSPORT] == "bluetooth"


async def test_lan_reauth_updates_only_after_verification(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, udp_client: Mock
) -> None:
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={
            **mock_config_entry.data,
            CONF_TRANSPORT: "lan",
            CONF_HOST: HOST,
            CONF_SERIAL: SERIAL,
        },
    )
    flow = BesenConfigFlow()
    flow.hass = hass
    flow.context = {"source": SOURCE_REAUTH, "entry_id": mock_config_entry.entry_id}
    await flow.async_step_reauth_confirm({CONF_PIN: "654321"})
    await flow._operation_task
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()):
        result = await flow.async_step_connection_done()
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PIN] == "654321"


async def test_listener_shared_until_final_user_releases(
    hass: HomeAssistant, hub: Mock
) -> None:
    first, second = await asyncio.gather(
        async_acquire_udp_hub(hass), async_acquire_udp_hub(hass)
    )
    assert first is second is hub
    await async_release_udp_hub(hass)
    hub.async_stop.assert_not_awaited()
    await async_release_udp_hub(hass)
    hub.async_stop.assert_awaited_once()


async def test_runtime_lan_ignores_missing_bluetooth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    udp_client: Mock,
    mock_ble_device: Mock,
    mock_besen_client: Mock,
    hub: Mock,
) -> None:
    mock_ble_device.return_value = None
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={
            **mock_config_entry.data,
            CONF_TRANSPORT: "lan",
            CONF_HOST: HOST,
            CONF_SERIAL: SERIAL,
        },
    )
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    mock_besen_client.async_start.assert_not_awaited()
    assert hass.states.get("switch.garage_charge").state == "on"
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    hub.async_stop.assert_awaited_once()


async def test_listener_bind_error_retries_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    udp_client: Mock,
    hub: Mock,
) -> None:
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={
            **mock_config_entry.data,
            CONF_TRANSPORT: "lan",
            CONF_HOST: HOST,
            CONF_SERIAL: SERIAL,
        },
    )
    hub.async_start.side_effect = CannotConnect("bind failed")
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    udp_client.async_start.assert_not_awaited()


async def test_runtime_failed_login_releases_listener(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    udp_client: Mock,
    hub: Mock,
) -> None:
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={
            **mock_config_entry.data,
            CONF_TRANSPORT: "lan",
            CONF_HOST: HOST,
            CONF_SERIAL: SERIAL,
        },
    )
    udp_client.async_start.side_effect = InvalidAuth("rejected")
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    hub.async_stop.assert_awaited_once()


async def test_reconfigure_recovers_identity_from_unloaded_device(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        connections={(dr.CONNECTION_BLUETOOTH, FIXTURE_ADDRESS)},
        serial_number=SERIAL,
    )
    flow = BesenConfigFlow()
    flow.hass = hass
    flow.context = {
        "source": SOURCE_RECONFIGURE,
        "entry_id": mock_config_entry.entry_id,
    }
    await flow.async_step_reconfigure()
    assert flow._pending_data[CONF_SERIAL] == SERIAL


async def test_reconfigure_rejects_unknown_identity(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, udp_client: Mock
) -> None:
    flow = flow_for(hass, mock_config_entry)
    del flow._pending_data[CONF_SERIAL]
    result = await flow.async_step_lan({CONF_HOST: HOST, CONF_PIN: FIXTURE_PIN})
    assert result["errors"] == {"base": "identity_unknown"}
    udp_client.async_start.assert_not_awaited()


async def test_reconfigure_rejects_different_charger(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, udp_client: Mock
) -> None:
    flow = flow_for(hass, mock_config_entry)
    udp_client.state = udp_client.state.updated(
        info=udp_client.state.info.updated(serial="1122334455667788")
    )
    original = dict(mock_config_entry.data)
    await flow.async_step_lan({CONF_HOST: HOST, CONF_PIN: FIXTURE_PIN})
    await flow._operation_task
    assert (await flow.async_step_connection_done())["errors"] == {
        "base": "wrong_device"
    }
    assert mock_config_entry.data == original


async def test_old_connection_must_release_before_lan(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    udp_client: Mock,
) -> None:
    mock_besen_client.is_connected = True
    mock_config_entry.runtime_data = Mock(client=mock_besen_client)
    flow = flow_for(hass, mock_config_entry)
    await flow.async_step_lan({CONF_HOST: HOST, CONF_PIN: FIXTURE_PIN})
    await flow._operation_task
    assert (await flow.async_step_connection_done())["errors"] == {
        "base": "cannot_connect"
    }
    udp_client.async_start.assert_not_awaited()


async def test_failed_restoration_requests_saved_entry_reload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
    udp_client: Mock,
) -> None:
    mock_besen_client.is_connected = False
    mock_besen_client.async_start.side_effect = CannotConnect("restore failed")
    mock_config_entry.runtime_data = Mock(client=mock_besen_client)
    flow = flow_for(hass, mock_config_entry)
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload:
        await flow.async_step_lan({CONF_HOST: HOST, CONF_PIN: FIXTURE_PIN})
        await flow._operation_task
        await hass.async_block_till_done()
    reload.assert_awaited_once_with(mock_config_entry.entry_id)


async def test_failed_lan_reauth_keeps_pin(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, udp_client: Mock
) -> None:
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={
            **mock_config_entry.data,
            CONF_TRANSPORT: "lan",
            CONF_HOST: HOST,
            CONF_SERIAL: SERIAL,
        },
    )
    flow = BesenConfigFlow()
    flow.hass = hass
    flow.context = {"source": SOURCE_REAUTH, "entry_id": mock_config_entry.entry_id}
    udp_client.async_start.side_effect = InvalidAuth("rejected")
    await flow.async_step_reauth_confirm({CONF_PIN: "654321"})
    await flow._operation_task
    result = await flow.async_step_connection_done()
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    assert mock_config_entry.data[CONF_PIN] == FIXTURE_PIN


async def test_invalid_lan_reauth_pin_never_connects(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, udp_client: Mock
) -> None:
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, CONF_TRANSPORT: "lan"}
    )
    flow = BesenConfigFlow()
    flow.hass = hass
    flow.context = {"source": SOURCE_REAUTH, "entry_id": mock_config_entry.entry_id}
    result = await flow.async_step_reauth_confirm({CONF_PIN: "12345"})
    assert result["errors"] == {"base": "invalid_auth"}
    udp_client.async_start.assert_not_awaited()


async def test_user_must_choose_a_connection(hass: HomeAssistant) -> None:
    flow = flow_for(hass)
    result = await flow.async_step_user({CONF_PIN: FIXTURE_PIN})
    assert result["errors"] == {"base": "choose_connection"}


async def test_second_reconfigure_is_blocked(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    context = {"source": SOURCE_RECONFIGURE, "entry_id": mock_config_entry.entry_id}
    first = await hass.config_entries.flow.async_init(DOMAIN, context=context)
    assert first["type"] is FlowResultType.MENU
    second = await hass.config_entries.flow.async_init(DOMAIN, context=context)
    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "already_in_progress"


async def test_lan_only_identity_updates_controls_and_diagnostics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    udp_client: Mock,
    mock_besen_client: Mock,
) -> None:
    address = f"lan:{SERIAL}"
    udp_client.address = address
    udp_client.state = udp_client.state.updated(
        info=udp_client.state.info.updated(address=address)
    )
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        unique_id=address,
        data={
            **mock_config_entry.data,
            CONF_ADDRESS: address,
            CONF_TRANSPORT: "lan",
            CONF_HOST: HOST,
            CONF_SERIAL: SERIAL,
        },
    )
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    (device,) = dr.async_entries_for_config_entry(
        dr.async_get(hass), mock_config_entry.entry_id
    )
    assert device.connections == set()
    assert device.identifiers == {(DOMAIN, SERIAL)}
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.garage_charging_current", "value": 6},
        blocking=True,
    )
    udp_client.async_set_charge_amps.assert_awaited_once_with(6)
    mock_besen_client.async_set_charge_amps.assert_not_awaited()
    publish_besen_state(
        udp_client,
        udp_client.state.updated(config=udp_client.state.config.updated(charge_amps=6)),
    )
    await hass.async_block_till_done()
    assert hass.states.get("number.garage_charging_current").state == "6"
    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert diagnostics["entry_data"][CONF_HOST] == "**REDACTED**"
    assert HOST not in repr(diagnostics)
    assert FIXTURE_PIN not in repr(diagnostics)
