"""Tests for explicit authentication failures and recovery in the BLE client."""

import asyncio
import logging
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

from besen.client import BesenClient
from besen.exceptions import InvalidAuth
from besen.models import BesenData
import pytest


@pytest.fixture
def client() -> BesenClient:
    """Create a client without opening a Bluetooth connection."""

    return BesenClient(
        address="AA:BB",
        pin="123456",
        ble_device_provider=lambda: None,
        logger=logging.getLogger(__name__),
    )


async def test_pin_rejection_is_published(client: BesenClient) -> None:
    """An explicit rejection reaches listeners and survives connection cleanup."""

    states: list[BesenData] = []
    client.add_listener(states.append)
    client._login_request_sent = True
    initial_state = client.state
    assert not initial_state.auth_failed
    await client._async_handle_packet(341, b"", "SERIAL")
    assert client.state.auth_failed
    assert not client.state.authenticated
    assert states[-1].auth_failed
    await client._disconnect_login_attempt("Connection closed after rejection")
    assert not client.state.available
    assert states[-1].auth_failed


@pytest.mark.parametrize(
    ("login_sent", "authenticated"), [(False, False), (True, True)]
)
async def test_unsolicited_rejection_does_not_require_reauth(
    client: BesenClient, login_sent: bool, authenticated: bool
) -> None:
    """Ignore rejection packets outside an active unauthenticated login."""

    client._login_request_sent = login_sent
    client._set_state(available=True, authenticated=authenticated)
    await client._async_handle_packet(341, b"", "SERIAL")
    assert not client.state.auth_failed
    assert client.state.authenticated is authenticated


async def test_queued_packet_cannot_revive_rejected_login(client: BesenClient) -> None:
    """A queued login response cannot authenticate a rejected connection."""

    client._login_request_sent = True
    await client._async_handle_packet(341, b"", "SERIAL")
    with patch.object(
        client, "_async_handle_packet_locked", new_callable=AsyncMock
    ) as handler:
        await client._async_handle_packet(2, b"", "SERIAL")
    handler.assert_not_awaited()
    assert client.state.auth_failed
    assert not client.state.authenticated


async def test_reconnect_rejection_stops_automatic_retries(
    client: BesenClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reconnect exposes InvalidAuth without retrying the rejected PIN forever."""

    async def reject_login() -> None:
        client._login_request_sent = True
        await client._async_handle_packet(341, b"", "SERIAL")

    monkeypatch.setattr("besen.client.RECONNECT_DELAY", 0)
    with patch.object(client, "_connect_once", side_effect=reject_login) as connect:
        await client._reconnect_loop()
    connect.assert_awaited_once()
    assert client.state.auth_failed
    assert not client.state.available
    client._schedule_reconnect()
    assert client._reconnect_task is None
    assert not client._reconnect_requested


async def test_watchdog_stops_after_pin_rejection(
    client: BesenClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The inactivity watchdog must not restart a rejected login."""

    client._login_request_sent = True
    await client._async_handle_packet(341, b"", "SERIAL")
    monkeypatch.setattr("besen.client.MESSAGE_TIMEOUT", 0)
    with patch.object(client, "_schedule_reconnect") as reconnect:
        await asyncio.wait_for(client._watchdog_loop(), 1)
    reconnect.assert_not_called()
    assert client.state.auth_failed


async def test_start_with_replacement_pin_clears_auth_failure(
    client: BesenClient,
) -> None:
    """An explicit new start clears the failure and can authenticate normally."""

    client._login_request_sent = True
    await client._async_handle_packet(341, b"", "SERIAL")
    client.pin = "654321"

    async def successful_login() -> None:
        client._set_state(available=True, authenticated=True, last_error=None)
        client._ready_event.set()

    with (
        patch.object(client, "_connect_once", side_effect=successful_login),
        patch.object(
            BesenClient, "is_connected", new_callable=PropertyMock, return_value=True
        ),
        patch.object(client, "_start_watchdog") as watchdog,
    ):
        await client.async_start()
    watchdog.assert_called_once()
    assert client.state.authenticated
    assert not client.state.auth_failed
    assert client.state.last_error is None


async def test_start_rejection_retains_typed_failure(client: BesenClient) -> None:
    """Startup still raises InvalidAuth and leaves a typed failure after cleanup."""

    async def reject_login() -> None:
        client._login_request_sent = True
        await client._async_handle_packet(341, b"", "SERIAL")

    with (
        patch.object(client, "_connect_once", side_effect=reject_login),
        pytest.raises(InvalidAuth),
    ):
        await client.async_start()
    assert client.state.auth_failed
    assert not client.state.available
    assert not client.state.authenticated


def test_transport_failure_is_not_auth_failure(client: BesenClient) -> None:
    """Unavailability or error-message text is not proof of PIN rejection."""

    listener = Mock()
    client.add_listener(listener)
    client._set_state(
        available=False,
        authenticated=False,
        last_error="The charger rejected the configured PIN",
    )
    assert not client.state.auth_failed
    assert not listener.call_args.args[0].auth_failed
