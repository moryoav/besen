"""Tests for the Besen BLE client."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import AsyncIterator, Callable
import logging
from types import SimpleNamespace
from typing import Any, cast

from besen import client as client_module
from besen.client import BesenClient
from besen.const import (
    NEW_BOARD_READ_UUID,
    NEW_BOARD_SERVICE_PREFIXES,
    NEW_BOARD_WRITE_UUID,
    READ_UUID,
    REV_BOARD_SERVICE_PREFIXES,
    REV_READ_UUID,
    REV_WRITE_UUID,
    WRITE_UUID,
)
from besen.exceptions import CannotConnect, CommandFailed, InvalidAuth, ProtocolError
from besen.models import BoardRevision, CharacteristicPair
from besen.protocol import PARSERS, build_command, parse_packet
from bleak.backends.device import BLEDevice
import pytest

EVSE_IDENTIFIER = "8949281891483449"


@pytest.fixture
async def charging_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[BesenClient, _FakeBleakClient]]:
    """Provide a connected charger with manually controlled command replies."""

    fake = _FakeBleakClient(_login_packets())
    client = _client(fake, monkeypatch)
    await client.async_start()
    monkeypatch.setattr(client, "_schedule_reconnect", lambda: None)
    fake.write_started = asyncio.Event()
    try:
        yield client, fake
    finally:
        await client.async_stop()


async def _start_charging_request(
    client: BesenClient, fake: _FakeBleakClient
) -> asyncio.Task[None]:
    """Start a command and wait until it reaches the Bluetooth transport."""

    assert fake.write_started is not None
    fake.write_started.clear()
    request = asyncio.create_task(client.async_start_charging(16))
    await asyncio.wait_for(fake.write_started.wait(), 1)
    return request


@pytest.mark.parametrize("phases", [1, 3])
async def test_charge_start_waits_for_reply(
    charging_client: tuple[BesenClient, _FakeBleakClient], phases: int
) -> None:
    """A written request waits for a matching reply without blocking heartbeats."""

    client, fake = charging_client
    client._set_state(info=client.state.info.updated(phases=phases))
    request = await _start_charging_request(client, fake)
    line_id = parse_packet(fake.writes[-1][1]).data[0]
    assert not request.done()
    await asyncio.wait_for(client._async_handle_packet(3, b"", EVSE_IDENTIFIER), 1)
    assert _written_commands(fake)[32771] == 1
    await client._async_handle_packet(7, bytes([line_id, 0, 1, 0, 16]), EVSE_IDENTIFIER)
    await request
    assert client.state.last_command is not None
    assert client.state.last_command.values["error_reason"] == "No error"
    assert client._charge_start_response is None
    assert client.is_connected


@pytest.mark.parametrize(
    ("reservation", "error", "message"),
    [
        (0, 1, "plug is not plugged in properly"),
        (2, 0, "system does not support reservation"),
        (0, 255, "Unknown charging error 255"),
        (255, 0, "Unknown reservation error 255"),
    ],
)
async def test_charge_start_rejection(
    charging_client: tuple[BesenClient, _FakeBleakClient],
    reservation: int,
    error: int,
    message: str,
) -> None:
    """Known and unknown rejection codes reach the action caller."""

    client, fake = charging_client
    request = await _start_charging_request(client, fake)
    await client._async_handle_packet(
        7, bytes([2, reservation, 0, error, 16]), EVSE_IDENTIFIER
    )
    with pytest.raises(CommandFailed, match=message):
        await request
    assert client._charge_start_response is None
    assert client.is_connected


async def test_charge_start_ignores_unrelated_replies(
    charging_client: tuple[BesenClient, _FakeBleakClient],
) -> None:
    """Unrelated or malformed replies cannot finish a charging request."""

    client, fake = charging_client
    client._set_state(charge=client.state.charge.updated(line_id=2))
    request = await _start_charging_request(client, fake)
    await client._async_handle_packet(7, b"\x02\x00\x01\x00\x10", "other charger")
    await client._async_handle_packet(7, b"\x01\x00\x01\x00\x10", EVSE_IDENTIFIER)
    await client._async_handle_packet(7, b"\x02", EVSE_IDENTIFIER)
    await client._async_handle_packet(8, b"\x02\x0b\x00", EVSE_IDENTIFIER)
    assert not request.done()
    await client._async_handle_packet(7, b"\x02\x00\x01\x00\x10", EVSE_IDENTIFIER)
    await request


@pytest.mark.parametrize("error", [0, 1], ids=["accepted", "rejected"])
@pytest.mark.parametrize(
    ("phases", "reported_line_id", "reply_line_id"),
    [
        (1, None, 1),
        (1, 1, 1),
        (3, None, 1),
        (3, None, 2),
        (3, 1, 1),
        (3, 2, 2),
    ],
    ids=[
        "single-phase-before-telemetry",
        "single-phase-connector-1",
        "three-phase-connector-1-before-telemetry",
        "three-phase-connector-2-before-telemetry",
        "three-phase-connector-1",
        "three-phase-connector-2",
    ],
)
async def test_charge_start_uses_reported_connector_id(
    charging_client: tuple[BesenClient, _FakeBleakClient],
    monkeypatch: pytest.MonkeyPatch,
    error: int,
    phases: int,
    reported_line_id: int | None,
    reply_line_id: int,
) -> None:
    """Both phase counts accept their replies before and after connector telemetry."""

    client, fake = charging_client
    client._set_state(
        info=client.state.info.updated(phases=phases),
        charge=client.state.charge.updated(line_id=reported_line_id),
    )
    monkeypatch.setattr(client_module, "CHARGE_START_TIMEOUT", 0.1)
    request = await _start_charging_request(client, fake)
    # Preserve the established single/three-phase wire request.
    assert parse_packet(fake.writes[-1][1]).data[0] == (2 if phases == 3 else 1)
    await client._async_handle_packet(
        7, bytes([reply_line_id, 0, 1, 0, 16]), "other charger"
    )
    assert not request.done()
    if reported_line_id is not None:
        await client._async_handle_packet(
            7, bytes([3, 0, 1, 0, 16]), EVSE_IDENTIFIER
        )
        assert not request.done()
    await client._async_handle_packet(
        7, bytes([reply_line_id, 0, int(error == 0), error, 16]), EVSE_IDENTIFIER
    )
    if error:
        with pytest.raises(CommandFailed, match="plug is not plugged in properly"):
            await request
    else:
        await request
    assert client.is_connected
    assert client._charge_start_response is None


async def test_charge_start_serializes_requests(
    charging_client: tuple[BesenClient, _FakeBleakClient],
) -> None:
    """A second start is sent only after the first reply is consumed."""

    client, fake = charging_client
    first = await _start_charging_request(client, fake)
    second = asyncio.create_task(client.async_start_charging(16))
    await asyncio.sleep(0)
    assert _written_commands(fake)[32775] == 1
    assert fake.write_started is not None
    fake.write_started.clear()
    await client._async_handle_packet(7, b"\x02\x00\x01\x00\x10", EVSE_IDENTIFIER)
    # Duplicate replies already queued for the first request must be ignored.
    await client._async_handle_packet(7, b"\x02\x00\x01\x00\x10", EVSE_IDENTIFIER)
    await first
    await asyncio.wait_for(fake.write_started.wait(), 1)
    assert _written_commands(fake)[32775] == 2
    assert not second.done()
    await client._async_handle_packet(7, b"\x02\x00\x00\x01\x10", EVSE_IDENTIFIER)
    with pytest.raises(CommandFailed, match="plug is not plugged in properly"):
        await second


@pytest.mark.parametrize("end_session", ["disconnect", "shutdown", "unavailable"])
async def test_charge_start_connection_ends(
    charging_client: tuple[BesenClient, _FakeBleakClient], end_session: str
) -> None:
    """Connection loss and unloading promptly release the pending action."""

    client, fake = charging_client
    request = await _start_charging_request(client, fake)
    if end_session == "disconnect":
        fake.is_connected = False
        client._disconnected(cast(Any, fake))
    elif end_session == "shutdown":
        await client.async_stop()
    else:
        client._set_state(available=False, authenticated=False)
    with pytest.raises(CommandFailed, match="disconnected before confirming"):
        await asyncio.wait_for(request, 1)
    assert client._charge_start_response is None


async def test_charge_start_write_failure(
    charging_client: tuple[BesenClient, _FakeBleakClient],
) -> None:
    """Transport errors preserve CommandFailed and clear the response waiter."""

    client, fake = charging_client
    fake.fail_write = True
    with pytest.raises(CommandFailed, match="Failed to send charge_start"):
        await client.async_start_charging()
    assert client._charge_start_response is None


@pytest.mark.parametrize("cancel", [False, True], ids=["timeout", "cancel"])
async def test_charge_start_abandons_session(
    charging_client: tuple[BesenClient, _FakeBleakClient],
    monkeypatch: pytest.MonkeyPatch,
    cancel: bool,
) -> None:
    """An unconfirmed request retires the session without retrying the action."""

    client, fake = charging_client
    monkeypatch.setattr(client_module, "CHARGE_START_TIMEOUT", 0.02)
    request = await _start_charging_request(client, fake)
    old_callback = fake.notification_callback
    assert old_callback is not None
    if cancel:
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
    else:
        with pytest.raises(CommandFailed, match="outcome is unknown"):
            await request
    assert fake.disconnected
    assert client._charge_start_response is None
    assert _written_commands(fake)[32775] == 1

    replacement = _FakeBleakClient(_login_packets())

    async def _establish_connection(*args: Any, **kwargs: Any) -> _FakeBleakClient:
        return replacement

    monkeypatch.setattr(client_module, "establish_connection", _establish_connection)
    monkeypatch.setattr(client_module, "CHARGE_START_TIMEOUT", 1)
    await client._connect_and_login()
    replacement.write_started = asyncio.Event()
    next_request = await _start_charging_request(client, replacement)
    old_callback(1, bytearray(_evse_packet(7, [2, 0, 1, 0, 16])))
    await asyncio.sleep(0)
    assert not next_request.done()
    assert replacement.notification_callback is not None
    replacement.notification_callback(1, bytearray(_evse_packet(7, [2, 0, 0, 1, 16])))
    with pytest.raises(CommandFailed, match="plug is not plugged in properly"):
        await next_request


async def test_charge_start_requires_authentication(
    charging_client: tuple[BesenClient, _FakeBleakClient],
) -> None:
    """A request cannot be sent during login or shutdown."""

    client, fake = charging_client
    client._set_state(authenticated=False)
    with pytest.raises(CommandFailed, match="not authenticated"):
        await client.async_start_charging()
    assert _written_commands(fake)[32775] == 0


async def test_charge_start_timeout_before_write_preserves_connection(
    charging_client: tuple[BesenClient, _FakeBleakClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timing out behind another write cannot retire an unused session."""

    client, fake = charging_client
    monkeypatch.setattr(client_module, "CHARGE_START_TIMEOUT", 0.01)
    async with client._command_lock:
        with pytest.raises(CommandFailed, match="Timed out"):
            await client.async_start_charging()
    assert _written_commands(fake)[32775] == 0
    assert client.is_connected
    assert client.state.authenticated
    fake.charge_start_reply = [2, 0, 1, 0, 16]
    await client.async_start_charging()


async def test_charge_start_cleanup_failure_preserves_timeout(
    charging_client: tuple[BesenClient, _FakeBleakClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed disconnect cannot hide a timeout or allow reuse before login."""

    client, fake = charging_client
    monkeypatch.setattr(client_module, "CHARGE_START_TIMEOUT", 0.01)
    fake.fail_disconnect = True
    try:
        with pytest.raises(CommandFailed, match="outcome is unknown"):
            await client.async_start_charging()
        assert client._charge_start_response is None
        assert not client.state.authenticated
        with pytest.raises(CommandFailed, match="not authenticated"):
            await client.async_start_charging()
        assert _written_commands(fake)[32775] == 1
    finally:
        fake.fail_disconnect = False


class _Characteristic:
    """Discovered GATT characteristic with explicit capabilities."""

    def __init__(self, uuid: str, properties: list[str]) -> None:
        self.uuid = uuid
        self.properties = properties


class _Service:
    """Fake BLE service."""

    def __init__(self, uuid: str, characteristics: list[_Characteristic]) -> None:
        """Initialize the service."""

        self.uuid = uuid
        self.characteristics = characteristics


class _Services(list[_Service]):
    """Minimal discovered service collection."""

    def get_characteristic(self, uuid: str) -> _Characteristic | None:
        return next(
            (
                char
                for service in self
                for char in service.characteristics
                if char.uuid == uuid
            ),
            None,
        )


class _BleDevice:
    """Fake BLE device."""


class _FakeBleakClient:
    """Fake bleak client that emits a login flow."""

    def __init__(
        self,
        packets: list[bytes],
        *,
        service_uuid: str | None = None,
        characteristics: list[_Characteristic] | None = None,
    ) -> None:
        """Initialize the fake client."""

        self.is_connected = True
        service_uuid = service_uuid or "0000fff0-0000-1000-8000-00805f9b34fb"
        if characteristics is None:
            read_uuid, write_uuid = READ_UUID, WRITE_UUID
            if service_uuid.startswith(NEW_BOARD_SERVICE_PREFIXES):
                read_uuid, write_uuid = NEW_BOARD_READ_UUID, NEW_BOARD_WRITE_UUID
            elif service_uuid.startswith(REV_BOARD_SERVICE_PREFIXES):
                read_uuid, write_uuid = REV_READ_UUID, REV_WRITE_UUID
            characteristics = [
                _Characteristic(read_uuid, ["read", "notify"]),
                _Characteristic(write_uuid, ["write", "write-without-response"]),
            ]
        self.services = _Services([_Service(service_uuid, characteristics)])
        self.packets = packets
        self.writes: list[tuple[str, bytes, bool]] = []
        self.stopped_notifications: list[str] = []
        self.disconnected = False
        self.fail_write = False
        self.fail_disconnect = False
        self.disconnect_on_notify = False
        self.disconnected_callback: Callable[[Any], None] | None = None
        self.write_started: asyncio.Event | None = None
        self.write_release: asyncio.Event | None = None
        self.notification_callback: Callable[[int, bytearray], None] | None = None
        self.charge_start_reply: list[int] | None = None

    async def start_notify(
        self,
        uuid: str,
        callback: Callable[[int, bytearray], None],
    ) -> None:
        """Start notifications and replay queued packets."""

        self.notification_callback = callback
        if self.disconnect_on_notify:
            self.is_connected = False
            self.disconnected = True
            assert self.disconnected_callback is not None
            self.disconnected_callback(self)
            return
        for packet in self.packets:
            callback(1, bytearray(packet))

    async def stop_notify(self, uuid: str) -> None:
        """Record stopped notifications."""

        self.stopped_notifications.append(uuid)

    async def disconnect(self) -> None:
        """Disconnect the fake client."""

        if self.fail_disconnect:
            raise OSError("disconnect failed")
        self.disconnected = True
        self.is_connected = False

    async def write_gatt_char(
        self,
        uuid: str,
        data: bytes,
        *,
        response: bool,
    ) -> None:
        """Record GATT writes."""

        if self.write_started is not None:
            self.write_started.set()
        if self.write_release is not None:
            await self.write_release.wait()
        if self.fail_write:
            raise OSError("write failed")
        char = self.services.get_characteristic(uuid)
        if char is None:
            raise OSError("Characteristic not found")
        property_name = "write" if response else "write-without-response"
        if property_name not in char.properties:
            raise OSError("Unsupported write mode")
        self.writes.append((uuid, data, response))
        if parse_packet(data).command == 32775 and self.charge_start_reply is not None:
            assert self.notification_callback is not None
            self.notification_callback(
                1, bytearray(_evse_packet(7, self.charge_start_reply))
            )


class _DelayedLoginBleakClient(_FakeBleakClient):
    """Fake client that emits stale traffic before a delayed login flow."""

    def __init__(self, delay: float) -> None:
        super().__init__([])
        self.delay = delay
        self.emitter: asyncio.Task[None] | None = None

    async def start_notify(
        self,
        uuid: str,
        callback: Callable[[int, bytearray], None],
    ) -> None:
        """Emit one stale heartbeat, then login packets after a delay."""

        del uuid
        callback(1, bytearray(_evse_packet(3)))

        async def _emit_login() -> None:
            await asyncio.sleep(self.delay)
            for packet in _login_packets():
                callback(1, bytearray(packet))

        self.emitter = asyncio.create_task(_emit_login())


def _login_data() -> list[int]:
    """Return a valid login payload."""

    data = bytearray(69)
    data[0] = 10
    data[1:16] = b"Besen\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    data[17:32] = b"BS20\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    data[33:49] = b"HW1\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    data[49:53] = bytes([0, 0, 0, 22])
    data[53] = 32
    data[54:69] = b"basic\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    return list(data)


def _login_packets() -> list[bytes]:
    """Return packets for a successful login flow."""

    return [
        _evse_packet(1, _login_data()),
        _evse_packet(2, _login_data()),
    ]


def _evse_packet(command: int, data: list[int] | None = None) -> bytes:
    """Build a charger-originated packet with its real placeholder password."""

    packet = bytearray(build_command(12345678, "123456", command, data))
    packet[5:13] = bytes.fromhex(EVSE_IDENTIFIER)
    packet[13:19] = b"\xff" * 6
    packet[-4:-2] = (sum(packet[:-4]) % 0xFFFF).to_bytes(2, "big")
    return bytes(packet)


def _written_commands(fake_client: _FakeBleakClient) -> Counter[int]:
    """Count protocol commands written to a fake charger."""

    return Counter(parse_packet(write[1]).command for write in fake_client.writes)


def _client(
    fake_client: _FakeBleakClient,
    monkeypatch: pytest.MonkeyPatch,
) -> BesenClient:
    """Create a client wired to fake BLE dependencies."""

    async def _establish_connection(*args: Any, **kwargs: Any) -> _FakeBleakClient:
        fake_client.disconnected_callback = kwargs["disconnected_callback"]
        return fake_client

    monkeypatch.setattr(client_module, "establish_connection", _establish_connection)
    return BesenClient(
        address="AA:BB:CC:DD:EE:FF",
        pin="123456",
        ble_device_provider=lambda: cast(BLEDevice, _BleDevice()),
        logger=logging.getLogger(__name__),
        advertised_name="ACP#Garage",
    )


def _client_with_connections(
    fake_clients: list[_FakeBleakClient],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[BesenClient, list[_FakeBleakClient]]:
    """Create a client that uses a new fake BLE connection for each attempt."""

    remaining = iter(fake_clients)
    established: list[_FakeBleakClient] = []

    async def _establish_connection(*args: Any, **kwargs: Any) -> _FakeBleakClient:
        del args
        fake_client = next(remaining)
        fake_client.disconnected_callback = kwargs["disconnected_callback"]
        established.append(fake_client)
        return fake_client

    monkeypatch.setattr(client_module, "establish_connection", _establish_connection)
    client = BesenClient(
        address="AA:BB:CC:DD:EE:FF",
        pin="123456",
        ble_device_provider=lambda: cast(BLEDevice, _BleDevice()),
        logger=logging.getLogger(__name__),
        advertised_name="ACP#Garage",
    )
    return client, established


@pytest.mark.parametrize(
    ("available", "authenticated"),
    [(False, True), (True, False), (False, False)],
)
def test_availability_logs_once_per_outage(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    available: bool,
    authenticated: bool,
) -> None:
    """Only usable-state transitions log, including a second independent outage."""

    client = _client(_FakeBleakClient([]), monkeypatch)
    with caplog.at_level(logging.INFO, logger=__name__):
        client._set_state(available=True, authenticated=True)
        assert not caplog.records
        client._set_state(
            available=available,
            authenticated=authenticated,
            last_error="Bluetooth connection lost",
        )
        for _ in range(3):
            client._set_state(
                available=False, authenticated=False, last_error="Retry failed"
            )
            client._set_state(available=True, authenticated=False, last_error=None)
        client._set_state(available=True, authenticated=True, last_error=None)
        client._set_state(available=True, authenticated=True)
        client._set_state(available=False, authenticated=False, last_error=None)
        client._set_state(available=True, authenticated=True)

    assert caplog.record_tuples == [
        (
            __name__,
            logging.INFO,
            "Besen ACP#Garage is unavailable: Bluetooth connection lost",
        ),
        (__name__, logging.INFO, "Besen ACP#Garage is available again"),
        (
            __name__,
            logging.INFO,
            "Besen ACP#Garage is unavailable: Connection or authentication lost",
        ),
        (__name__, logging.INFO, "Besen ACP#Garage is available again"),
    ]


@pytest.mark.asyncio
async def test_client_login_selects_new_board_characteristics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful login marks the client ready and selects new board UUIDs."""

    fake_bleak = _FakeBleakClient(
        _login_packets(),
        service_uuid=f"{NEW_BOARD_SERVICE_PREFIXES[0]}0000-1000-8000-00805f9b34fb",
    )
    client = _client(fake_bleak, monkeypatch)

    await client.async_start()
    await client.async_set_charge_amps(16)
    await client.async_stop()

    assert client.state.info.manufacturer == "Besen"
    assert client.state.info.model == "BS20"
    assert client.state.info.board_revision == BoardRevision.NEW
    assert fake_bleak.writes
    assert {write[0] for write in fake_bleak.writes} == {NEW_BOARD_WRITE_UUID}
    assert all(write[2] is False for write in fake_bleak.writes)
    assert fake_bleak.stopped_notifications == [NEW_BOARD_READ_UUID]
    assert fake_bleak.disconnected is True


@pytest.mark.asyncio
async def test_client_public_commands_and_listeners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public command helpers send commands and listener removal works."""

    fake_bleak = _FakeBleakClient(_login_packets())
    fake_bleak.charge_start_reply = [2, 0, 1, 0, 16]
    client = _client(fake_bleak, monkeypatch)
    updates: list[bool] = []

    remove_listener = client.add_listener(lambda data: updates.append(data.available))

    await client.async_start()
    await client.async_start_charging()
    await client.async_stop_charging()
    await client.async_set_lcd_brightness(150)
    await client.async_set_temperature_unit("Fahrenheit")
    await client.async_set_temperature_unit("Celcius")
    await client.async_set_language("Deutsch")
    await client.async_set_device_name("Garage")
    assert client.state.config.lcd_brightness == 100
    assert client.state.config.temperature_unit == "Celsius"
    assert client.state.config.language == "Deutsch"
    update_count = len(updates)
    remove_listener()
    client._set_state(available=True)

    with pytest.raises(CommandFailed, match="Unsupported temperature unit"):
        await client.async_set_temperature_unit("Kelvin")
    with pytest.raises(CommandFailed, match="Unsupported language"):
        await client.async_set_language("Klingon")
    with pytest.raises(CommandFailed, match="Device name cannot be empty"):
        await client.async_set_device_name("   ")

    assert updates
    assert len(updates) == update_count
    await client.async_stop()


@pytest.mark.asyncio
async def test_client_selects_revised_and_old_characteristics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Characteristic selection handles revised and old boards."""

    revised_fake = _FakeBleakClient(
        _login_packets(),
        service_uuid=f"{REV_BOARD_SERVICE_PREFIXES[0]}0000-1000-8000-00805f9b0131",
    )
    revised = _client(revised_fake, monkeypatch)
    await revised.async_start()
    await revised.async_stop()

    old_fake = _FakeBleakClient(_login_packets())
    old = _client(old_fake, monkeypatch)
    await old.async_start()
    await old.async_stop()

    assert revised.state.info.board_revision == BoardRevision.REVISED
    assert old.state.info.board_revision == BoardRevision.OLD
    assert revised_fake.stopped_notifications == [REV_READ_UUID]
    assert {write[0] for write in revised_fake.writes} == {REV_WRITE_UUID}
    assert {write[0] for write in old_fake.writes} == {WRITE_UUID}


@pytest.mark.parametrize(
    ("write_properties", "response"),
    [
        (["read", "write"], True),
        (["write-without-response"], False),
        (["write", "write-without-response"], False),
    ],
    ids=["acknowledged-only", "unacknowledged-only", "both-modes"],
)
@pytest.mark.asyncio
async def test_single_phase_login_uses_supported_write_mode(
    monkeypatch: pytest.MonkeyPatch,
    write_properties: list[str],
    response: bool,
) -> None:
    """Issue #1's FFF1/FFF2 layout must work through login and commands."""

    login = bytearray(69)
    login[0] = 1
    login[1:16] = b"EVSE".ljust(15, b"\x00")
    login[17:32] = b"BS20".ljust(15, b"\x00")
    login[33:49] = b"C.3251.114A0083".ljust(16, b"\x00")
    login[49:53] = (7040).to_bytes(4, "big")
    login[53] = 32
    login[54:69] = b"WWW.EVSE.COM".ljust(15, b"\x00")
    fake = _FakeBleakClient(
        [_evse_packet(1, list(login)), _evse_packet(2, list(login))],
        characteristics=[
            _Characteristic(READ_UUID, ["read", "notify"]),
            _Characteristic(WRITE_UUID, write_properties),
        ],
    )
    client = _client(fake, monkeypatch)
    try:
        await client.async_start()
        assert client.state.authenticated
        assert client.state.info.phases == 1
        assert client.state.info.output_power == 7040
        assert client.state.info.output_max_amps == 32
        assert client.state.info.hardware_version == "C.3251.114A0083"
        await client.async_set_charge_amps(16)
        client._set_state(charge=client.state.charge.updated(line_id=1))
        fake.charge_start_reply = [1, 0, 1, 0, 16]
        await client.async_start_charging(16)
        assert client.state.last_command is not None
        assert client.state.last_command.values["line_id"] == 1
        assert client.is_connected
        assert fake.writes
        assert all(write[2] is response for write in fake.writes)
    finally:
        await client.async_stop()


@pytest.mark.parametrize("read_properties", [["notify"], ["indicate"]])
@pytest.mark.asyncio
async def test_characteristic_selection_uses_complete_pair(
    monkeypatch: pytest.MonkeyPatch, read_properties: list[str]
) -> None:
    """A misleading service prefix cannot override a usable discovered pair."""

    fake = _FakeBleakClient(
        _login_packets(),
        service_uuid=f"{NEW_BOARD_SERVICE_PREFIXES[0]}0000-1000-8000-00805f9b34fb",
        characteristics=[
            _Characteristic(NEW_BOARD_READ_UUID, ["read"]),
            _Characteristic(READ_UUID, read_properties),
            _Characteristic(WRITE_UUID, ["write"]),
        ],
    )
    client = _client(fake, monkeypatch)
    try:
        await client.async_start()
        assert client.state.info.board_revision == BoardRevision.OLD
        assert {write[0] for write in fake.writes} == {WRITE_UUID}
    finally:
        await client.async_stop()


@pytest.mark.parametrize(
    "characteristics",
    [
        [],
        [_Characteristic(WRITE_UUID, ["write"])],
        [_Characteristic(READ_UUID, ["notify"])],
        [_Characteristic(READ_UUID, ["read"]), _Characteristic(WRITE_UUID, ["write"])],
        [_Characteristic(READ_UUID, ["notify"]), _Characteristic(WRITE_UUID, ["read"])],
    ],
    ids=["empty", "missing-notify", "missing-write", "not-notifiable", "not-writable"],
)
@pytest.mark.asyncio
async def test_unusable_gatt_layout_fails_before_notifications(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    characteristics: list[_Characteristic],
) -> None:
    """Missing characteristics report discovery details without issuing writes."""

    fake = _FakeBleakClient(_login_packets(), characteristics=characteristics)
    client = _client(fake, monkeypatch)
    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(CannotConnect, match="No supported Besen GATT"),
    ):
        await client._connect_once()
    assert fake.disconnected
    assert not fake.writes
    assert not fake.stopped_notifications
    assert "Discovered Besen GATT services and characteristics" in caplog.text


@pytest.mark.asyncio
async def test_write_mode_is_rediscovered_on_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh connection uses its own GATT properties, not cached write mode."""

    first = _FakeBleakClient(
        _login_packets(),
        characteristics=[
            _Characteristic(READ_UUID, ["notify"]),
            _Characteristic(WRITE_UUID, ["write"]),
        ],
    )
    second = _FakeBleakClient(_login_packets())
    client, _ = _client_with_connections([first, second], monkeypatch)
    try:
        await client.async_start()
        await client.async_stop()
        await client.async_start()
        assert client.state.authenticated
        assert first.writes and second.writes
        assert all(write[2] is True for write in first.writes)
        assert all(write[2] is False for write in second.writes)
    finally:
        await client.async_stop()


@pytest.mark.asyncio
async def test_client_raises_invalid_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """A charger auth rejection raises InvalidAuth."""

    fake_bleak = _FakeBleakClient([_evse_packet(1, _login_data()), _evse_packet(341)])
    client = _client(fake_bleak, monkeypatch)

    with pytest.raises(InvalidAuth):
        await client.async_start()

    assert client.state.authenticated is False
    assert fake_bleak.disconnected is True
    await client.async_stop()


@pytest.mark.asyncio
async def test_client_raises_when_ble_device_missing() -> None:
    """Missing connectable Bluetooth devices fail before connecting."""

    client = BesenClient(
        address="AA:BB:CC:DD:EE:FF",
        pin="123456",
        ble_device_provider=lambda: None,
        logger=logging.getLogger(__name__),
    )

    with pytest.raises(CannotConnect, match="No connectable Bluetooth path"):
        await client.async_start()


@pytest.mark.asyncio
async def test_client_marks_unavailable_when_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BLE write failures raise CommandFailed and mark the state unavailable."""

    fake_bleak = _FakeBleakClient(_login_packets())
    client = _client(fake_bleak, monkeypatch)
    await client.async_start()

    fake_bleak.fail_write = True

    with pytest.raises(CommandFailed, match="Failed to send set_output_amps"):
        await client.async_set_charge_amps(16)

    assert client.state.available is False
    assert client.state.last_error == "Failed to send set_output_amps: write failed"
    await client.async_stop()


@pytest.mark.asyncio
async def test_client_connect_timeout_and_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connection timeout and establish failures raise CannotConnect."""

    silent_connections = [_FakeBleakClient([]) for _ in range(3)]
    timeout_client, established = _client_with_connections(
        silent_connections,
        monkeypatch,
    )
    monkeypatch.setattr(client_module, "SILENT_LOGIN_TIMEOUT", 0.01)
    monkeypatch.setattr(client_module, "RECONNECT_DELAY", 0)

    with pytest.raises(CannotConnect, match="Timed out"):
        await timeout_client.async_start()

    assert established == silent_connections
    assert all(connection.disconnected for connection in silent_connections)
    assert timeout_client.is_connected is False

    async def _fail_connect(*args: Any, **kwargs: Any) -> _FakeBleakClient:
        del args, kwargs
        raise OSError("no route")

    monkeypatch.setattr(client_module, "establish_connection", _fail_connect)
    failing_client = _client(_FakeBleakClient([]), monkeypatch)
    monkeypatch.setattr(client_module, "establish_connection", _fail_connect)

    with pytest.raises(CannotConnect, match="Unable to connect"):
        await failing_client.async_start()


@pytest.mark.asyncio
async def test_client_retries_completely_silent_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two silent connections are replaced before a third login succeeds."""

    first = _FakeBleakClient([])
    second = _FakeBleakClient([])
    successful = _FakeBleakClient(_login_packets())
    client, established = _client_with_connections(
        [first, second, successful],
        monkeypatch,
    )
    monkeypatch.setattr(client_module, "SILENT_LOGIN_TIMEOUT", 0.01)
    monkeypatch.setattr(client_module, "RECONNECT_DELAY", 0)

    await client.async_start()

    assert established == [first, second, successful]
    assert first.disconnected is True
    assert second.disconnected is True
    assert successful.disconnected is False
    assert client.state.authenticated is True
    await client.async_stop()


@pytest.mark.asyncio
async def test_client_keeps_live_stale_session_open_for_delayed_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normal traffic extends login wait while pre-auth heartbeats stay unanswered."""

    fake_bleak = _DelayedLoginBleakClient(0.02)
    client = _client(fake_bleak, monkeypatch)
    monkeypatch.setattr(client_module, "SILENT_LOGIN_TIMEOUT", 0.01)
    monkeypatch.setattr(client_module, "LOGIN_TIMEOUT", 0.05)

    await client.async_start()
    async with client._packet_lock:
        pass

    assert client.state.authenticated is True
    assert fake_bleak.disconnected is False
    assert _written_commands(fake_bleak)[32771] == 0
    await client.async_stop()


@pytest.mark.asyncio
async def test_client_cleans_up_incomplete_non_silent_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial login uses the total timeout and releases its BLE client."""

    incomplete = _FakeBleakClient([_login_packets()[0]])
    client, established = _client_with_connections([incomplete], monkeypatch)
    monkeypatch.setattr(client_module, "SILENT_LOGIN_TIMEOUT", 0.01)
    monkeypatch.setattr(client_module, "LOGIN_TIMEOUT", 0.02)

    with pytest.raises(CannotConnect, match="Timed out"):
        await client.async_start()

    assert established == [incomplete]
    assert incomplete.disconnected is True
    assert client.is_connected is False
    assert client.state.available is False
    await client.async_stop()


@pytest.mark.asyncio
async def test_client_gates_repeated_login_packets_and_clock_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated charger login beacons produce one reply and one refresh."""

    fake_bleak = _FakeBleakClient(_login_packets() * 5)
    client = _client(fake_bleak, monkeypatch)

    await client.async_start()
    async with client._packet_lock:
        pass
    await client._async_handle_packet(3, b"", client.state.info.serial or "")
    await client._async_handle_packet(3, b"", client.state.info.serial or "")

    commands = _written_commands(fake_bleak)
    clock_packets = [
        parse_packet(write[1])
        for write in fake_bleak.writes
        if parse_packet(write[1]).command == 33025
    ]
    assert commands[32770] == 1
    assert commands[32769] == 1
    assert commands[33042] == 1
    assert commands[33030] == 1
    assert commands[32771] == 2
    assert sum(packet.data[0] == 1 for packet in clock_packets) == 1
    await client.async_stop()


@pytest.mark.asyncio
async def test_client_requires_login_request_before_confirming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An early retained cmd2 cannot authenticate the new GATT connection."""

    packets = [
        _evse_packet(2, _login_data()),
        _evse_packet(1, _login_data()),
        _evse_packet(2, _login_data()),
    ]
    fake_bleak = _FakeBleakClient(packets)
    client = _client(fake_bleak, monkeypatch)

    await client.async_start()
    async with client._packet_lock:
        pass

    commands = _written_commands(fake_bleak)
    assert commands[32770] == 1
    assert commands[32769] == 1
    assert client.state.authenticated is True
    await client.async_stop()


@pytest.mark.asyncio
async def test_client_rate_limits_but_retries_unanswered_login_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated cmd1 can retry a lost write without creating a tight storm."""

    fake_bleak = _FakeBleakClient(_login_packets())
    client = _client(fake_bleak, monkeypatch)
    await client.async_start()
    async with client._packet_lock:
        pass
    baseline = _written_commands(fake_bleak)[32770]
    client._set_state(authenticated=False)
    client._last_login_request = None
    clock = [100.0]
    with monkeypatch.context() as clock_patch:
        clock_patch.setattr(
            "besen.client.time.monotonic",
            lambda: clock[0],
        )
        await client._async_handle_packet(
            1,
            bytes(_login_data()),
            EVSE_IDENTIFIER,
        )
        clock[0] = 101.0
        await client._async_handle_packet(
            1,
            bytes(_login_data()),
            EVSE_IDENTIFIER,
        )
        clock[0] = 106.0
        await client._async_handle_packet(
            1,
            bytes(_login_data()),
            EVSE_IDENTIFIER,
        )

    assert _written_commands(fake_bleak)[32770] == baseline + 2
    await client.async_stop()


@pytest.mark.asyncio
async def test_client_waits_out_stale_session_then_logs_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-login traffic gets no heartbeat until a fresh login exchange."""

    first = _FakeBleakClient(_login_packets())
    reconnected = _FakeBleakClient([_evse_packet(3), *_login_packets()])
    client, established = _client_with_connections([first, reconnected], monkeypatch)

    await client.async_start()
    async with client._packet_lock:
        pass
    await client._connect_and_login()
    async with client._packet_lock:
        pass

    assert established == [first, reconnected]
    assert first.disconnected is True
    assert client.state.authenticated is True
    assert _written_commands(reconnected)[32770] == 1
    assert _written_commands(reconnected)[32769] == 1
    assert _written_commands(reconnected)[32771] == 0

    assert first.disconnected_callback is not None
    first.disconnected_callback(first)
    assert client.state.available is True
    assert client.state.authenticated is True
    await client.async_stop()


@pytest.mark.asyncio
async def test_new_client_does_not_authenticate_from_operational_traffic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ordinary packets never stand in for the charger login exchange."""

    ordinary = _FakeBleakClient([_evse_packet(3)])
    client, established = _client_with_connections([ordinary], monkeypatch)
    monkeypatch.setattr(client_module, "SILENT_LOGIN_TIMEOUT", 0.01)
    monkeypatch.setattr(client_module, "LOGIN_TIMEOUT", 0.02)

    with pytest.raises(CannotConnect, match="Timed out"):
        await client.async_start()

    assert established == [ordinary]
    assert ordinary.writes == []
    assert ordinary.disconnected is True
    assert client.state.authenticated is False


@pytest.mark.asyncio
async def test_heartbeat_before_serial_is_deferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pre-login heartbeat cannot fail a background packet task."""

    client = _client(_FakeBleakClient([]), monkeypatch)

    await client._async_handle_packet(3, b"", "4e61bc0000000000")

    assert client.state.info.serial is None
    assert client.state.authenticated is False


@pytest.mark.asyncio
async def test_client_packet_handler_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Packet handler updates state for command families."""

    fake_bleak = _FakeBleakClient(_login_packets())
    client = _client(fake_bleak, monkeypatch)
    await client.async_start()

    monkeypatch.setitem(PARSERS, 4, lambda data, ident: {"line_id": 1})
    monkeypatch.setitem(PARSERS, 5, lambda data, ident: {"session_energy": 2.5})
    monkeypatch.setitem(PARSERS, 257, lambda data, ident: {"rssi": -50})
    monkeypatch.setitem(
        PARSERS,
        262,
        lambda data, ident: {"hardware_version": "HW2"},
    )
    monkeypatch.setitem(
        PARSERS,
        7,
        lambda data, ident: {"error_reason": "Denied"},
    )
    monkeypatch.setitem(
        PARSERS,
        8,
        lambda data, ident: {"stop_result": "Card swiping stop"},
    )

    await client._async_handle_packet(3, b"", "")
    await client._async_handle_packet(4, b"", "")
    await client._async_handle_packet(5, b"", "")
    await client._async_handle_packet(257, b"", "")
    await client._async_handle_packet(262, b"", "")
    await client._async_handle_packet(7, b"", "")
    await client._async_handle_packet(8, b"", "")

    def _raise_parser(data: bytes, identifier: str) -> dict[str, Any]:
        del data, identifier
        raise ProtocolError("bad")

    monkeypatch.setitem(PARSERS, 999, _raise_parser)
    await client._async_handle_packet(999, b"", "")

    assert client.state.charge.line_id == 1
    assert client.state.charge.session_energy == 2.5
    assert client.state.config.rssi == -50
    assert client.state.info.hardware_version == "HW2"
    assert client.state.last_command is not None
    assert client.state.last_command.command == "charge_stop"
    await client.async_stop()


@pytest.mark.asyncio
async def test_client_disconnect_notification_and_send_preconditions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disconnect, malformed notifications, and send preconditions are handled."""

    fake_bleak = _FakeBleakClient(_login_packets())
    client = _client(fake_bleak, monkeypatch)
    await client.async_start()

    scheduled = False

    def _schedule_reconnect() -> None:
        nonlocal scheduled
        scheduled = True

    monkeypatch.setattr(client, "_schedule_reconnect", _schedule_reconnect)
    client._disconnected(cast(Any, fake_bleak))

    packet = bytearray(build_command(12345678, "123456", 32771, [1]))
    packet[10] ^= 0xFF
    client._notification(1, packet)

    assert scheduled is True
    assert client.state.available is False
    assert client.state.last_error == "Bluetooth connection lost"

    disconnected = BesenClient(
        address="AA:BB:CC:DD:EE:FF",
        pin="123456",
        ble_device_provider=lambda: cast(BLEDevice, _BleDevice()),
        logger=logging.getLogger(__name__),
    )
    with pytest.raises(CommandFailed, match="not connected"):
        await disconnected._send_command(32770, None, name="login_request")

    disconnected._client = cast(Any, _FakeBleakClient([]))
    disconnected._characteristics = CharacteristicPair(
        read_uuid=READ_UUID,
        write_uuid=WRITE_UUID,
        board_revision=BoardRevision.OLD,
    )
    with pytest.raises(CommandFailed, match="serial is not known"):
        await disconnected._send_command(32770, None, name="login_request")

    client._set_state(info=client.state.info.updated(phases=1))
    assert client._charge_start_payload(6)[0] == 1
    client._update_info()
    client._set_state(
        info=client.state.info.updated(
            board_revision=BoardRevision.REVISED,
            software_version=None,
        )
    )
    client._update_info(hardware_version="fallback")
    assert client.state.info.hardware_version == "fallback"
    assert client.state.info.software_version == "fallback"
    await client.async_stop()


@pytest.mark.asyncio
async def test_disconnect_during_initial_login_has_one_connection_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A startup disconnect cannot launch a parallel reconnect workflow."""

    fake_bleak = _FakeBleakClient([])
    client, established = _client_with_connections([fake_bleak], monkeypatch)
    monkeypatch.setattr(client_module, "SILENT_LOGIN_TIMEOUT", 60)
    monkeypatch.setattr(client_module, "RECONNECT_DELAY", 60)
    start_task = asyncio.create_task(client.async_start())
    for _ in range(10):
        await asyncio.sleep(0)
        if fake_bleak.disconnected_callback is not None:
            break

    assert fake_bleak.disconnected_callback is not None
    fake_bleak.is_connected = False
    fake_bleak.disconnected = True
    fake_bleak.disconnected_callback(fake_bleak)
    await asyncio.sleep(0)

    assert established == [fake_bleak]
    assert client._connect_lock.locked() is True
    assert client._reconnect_task is None
    assert client.state.available is False

    start_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await start_task
    await client.async_stop()


@pytest.mark.asyncio
async def test_async_stop_cancels_live_initial_login_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shutdown waits for startup cleanup and prevents later reconnect attempts."""

    fake_bleak = _FakeBleakClient([])
    client, established = _client_with_connections([fake_bleak], monkeypatch)
    monkeypatch.setattr(client_module, "SILENT_LOGIN_TIMEOUT", 60)
    start_task = asyncio.create_task(client.async_start())
    for _ in range(10):
        await asyncio.sleep(0)
        if fake_bleak.disconnected_callback is not None:
            break

    assert established == [fake_bleak]
    assert fake_bleak.disconnected_callback is not None
    await client.async_stop()
    await asyncio.sleep(0)

    assert start_task.cancelled() is True
    assert established == [fake_bleak]
    assert fake_bleak.disconnected is True
    assert client._client is None


@pytest.mark.asyncio
async def test_disconnect_during_start_notify_is_not_clobbered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A subscribe-time disconnect remains unavailable and aborts setup."""

    fake_bleak = _FakeBleakClient([])
    fake_bleak.disconnect_on_notify = True
    client = _client(fake_bleak, monkeypatch)

    with pytest.raises(CannotConnect, match="notifications were starting"):
        await client.async_start()

    assert client.state.available is False
    assert client.state.authenticated is False
    assert client._reconnect_task is None
    await client.async_stop()


@pytest.mark.asyncio
async def test_failed_disconnect_retains_client_handle_for_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed teardown cannot be followed by a second BLE connection."""

    fake_bleak = _FakeBleakClient(_login_packets())
    client = _client(fake_bleak, monkeypatch)
    await client.async_start()
    async with client._packet_lock:
        pass
    fake_bleak.fail_disconnect = True

    with pytest.raises(CannotConnect, match="release the existing"):
        await client._disconnect_client()

    assert cast(Any, client._client) is fake_bleak
    assert fake_bleak.is_connected is True

    fake_bleak.fail_disconnect = False
    await client.async_stop()
    assert fake_bleak.disconnected is True


@pytest.mark.asyncio
async def test_queued_command_revalidates_client_inside_write_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A queued write uses the current client rather than a retired session."""

    first = _FakeBleakClient(_login_packets())
    client = _client(first, monkeypatch)
    await client.async_start()
    async with client._packet_lock:
        pass
    first_write_count = len(first.writes)
    replacement = _FakeBleakClient([])

    await client._command_lock.acquire()
    send_task = asyncio.create_task(client._send_heartbeat())
    await asyncio.sleep(0)
    first.is_connected = False
    first.disconnected = True
    client._client = cast(Any, replacement)
    client._command_lock.release()
    await send_task

    assert len(first.writes) == first_write_count
    assert _written_commands(replacement)[32771] == 1
    await client.async_stop()


@pytest.mark.asyncio
async def test_stale_write_failure_cannot_break_replacement_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retired client's late write error cannot mutate the new generation."""

    first = _FakeBleakClient(_login_packets())
    replacement = _FakeBleakClient(_login_packets())
    client, established = _client_with_connections([first, replacement], monkeypatch)
    await client.async_start()
    async with client._packet_lock:
        pass
    first.write_started = asyncio.Event()
    first.write_release = asyncio.Event()
    first.fail_write = True
    stale_write = asyncio.create_task(client._send_heartbeat())
    await first.write_started.wait()

    monkeypatch.setattr(client, "_schedule_reconnect", lambda: None)
    assert first.disconnected_callback is not None
    first.is_connected = False
    first.disconnected = True
    first.disconnected_callback(first)
    reconnect = asyncio.create_task(client._connect_and_login())
    for _ in range(10):
        await asyncio.sleep(0)
        if established == [first, replacement]:
            break

    assert established == [first, replacement]
    first.write_release.set()
    with pytest.raises(CommandFailed, match="Failed to send heartbeat"):
        await stale_write
    await reconnect
    async with client._packet_lock:
        pass

    assert cast(Any, client._client) is replacement
    assert client._connection_error is None
    assert client.state.available is True
    assert client.state.authenticated is True
    await client.async_stop()


@pytest.mark.asyncio
async def test_reconnect_loop_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reconnect owner persists through a failure and validates success."""

    client = _client(_FakeBleakClient([]), monkeypatch)
    replacement = _FakeBleakClient([])
    attempts = 0

    async def _connect_and_login() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise CannotConnect("temporary failure")
        client._client = cast(Any, replacement)
        client._characteristics = CharacteristicPair(
            read_uuid=READ_UUID,
            write_uuid=WRITE_UUID,
            board_revision=BoardRevision.OLD,
        )
        client._set_state(available=True, authenticated=True)

    monkeypatch.setattr(client, "_connect_and_login", _connect_and_login)
    monkeypatch.setattr(client_module, "RECONNECT_DELAY", 0)

    await client._reconnect_loop()

    assert attempts == 2
    assert client.state.authenticated is True
    await client.async_stop()


@pytest.mark.asyncio
async def test_watchdog_marks_unavailable_and_requests_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Notification inactivity marks state down and invokes reconnection."""

    client = _client(_FakeBleakClient([]), monkeypatch)
    client._last_message = 0
    scheduled = False

    def _schedule_reconnect() -> None:
        nonlocal scheduled
        scheduled = True
        client._stopping = True

    monkeypatch.setattr(client, "_schedule_reconnect", _schedule_reconnect)
    monkeypatch.setattr(client_module, "MESSAGE_TIMEOUT", 0)
    with monkeypatch.context() as clock_patch:
        clock_patch.setattr("besen.client.time.monotonic", lambda: 10.0)
        await client._watchdog_loop()

    assert scheduled is True
    assert client.state.available is False
    assert client.state.authenticated is False
    assert client.state.last_error == "No notifications received; reconnecting"


@pytest.mark.asyncio
async def test_async_stop_reports_persistent_disconnect_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shutdown retries teardown and records a link it could not release."""

    fake_bleak = _FakeBleakClient(_login_packets())
    client = _client(fake_bleak, monkeypatch)
    await client.async_start()
    async with client._packet_lock:
        pass
    fake_bleak.fail_disconnect = True

    await client.async_stop()

    assert cast(Any, client._client) is fake_bleak
    assert client.state.available is False
    assert client.state.last_error == (
        "Unable to release the existing Besen BLE connection"
    )

    fake_bleak.fail_disconnect = False
    await client._disconnect_client()


async def test_long_watchdog_outage_logs_once(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Watchdog cycles beyond ten minutes remain one outage, not periodic warnings."""

    client = _client(_FakeBleakClient([]), monkeypatch)
    client._set_state(available=True, authenticated=True)
    client._last_message = 0
    clock = [100.0]
    attempts = 0

    def _schedule_reconnect() -> None:
        nonlocal attempts
        attempts += 1
        clock[0] += 700.0
        if attempts == 3:
            client._stopping = True

    monkeypatch.setattr(client, "_schedule_reconnect", _schedule_reconnect)
    monkeypatch.setattr(client_module, "MESSAGE_TIMEOUT", 0)
    with (
        monkeypatch.context() as clock_patch,
        caplog.at_level(logging.INFO, logger=__name__),
    ):
        clock_patch.setattr(
            client_module, "time", SimpleNamespace(monotonic=lambda: clock[0])
        )
        await client._watchdog_loop()
        client._stopping = False
        client._set_state(available=True, authenticated=False)
        client._set_state(available=True, authenticated=True)

    assert attempts == 3
    assert caplog.record_tuples == [
        (
            __name__,
            logging.INFO,
            "Besen ACP#Garage is unavailable: No notifications received; reconnecting",
        ),
        (__name__, logging.INFO, "Besen ACP#Garage is available again"),
    ]


async def test_disconnect_recovery_waits_for_authentication(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A brief disconnect logs immediately; opening GATT alone is not recovery."""

    first = _FakeBleakClient(_login_packets())
    second = _FakeBleakClient([])
    client, _ = _client_with_connections([first, second], monkeypatch)
    monkeypatch.setattr(client, "_schedule_reconnect", lambda: None)
    # Hold the level across start and stop: outside it the logger emits DEBUG.
    with caplog.at_level(logging.INFO, logger=__name__):
        await client.async_start()
        try:
            first.is_connected = False
            client._disconnected(cast(Any, first))
            client._disconnected(cast(Any, first))
            reconnect = asyncio.create_task(client._connect_and_login())
            for _ in range(10):
                await asyncio.sleep(0)
                if second.notification_callback is not None:
                    break
            assert second.notification_callback is not None
            state_before_login = client.state
            assert state_before_login.available
            assert not state_before_login.authenticated
            assert len(caplog.records) == 1
            for packet in _login_packets():
                second.notification_callback(1, bytearray(packet))
            await asyncio.wait_for(reconnect, 1)
            assert client.state.authenticated
        finally:
            await client.async_stop()

    assert caplog.record_tuples == [
        (
            __name__,
            logging.INFO,
            "Besen ACP#Garage is unavailable: Bluetooth connection lost",
        ),
        (__name__, logging.INFO, "Besen ACP#Garage is available again"),
    ]


async def test_silent_reconnect_retries_do_not_repeat_outage_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Repeated silent logins retain debug diagnostics and one info-level pair."""

    first = _FakeBleakClient(_login_packets())
    silent = [_FakeBleakClient([]), _FakeBleakClient([])]
    second = _FakeBleakClient(_login_packets())
    client, established = _client_with_connections(
        [first, *silent, second], monkeypatch
    )
    monkeypatch.setattr(client, "_schedule_reconnect", lambda: None)
    monkeypatch.setattr(client_module, "SILENT_LOGIN_TIMEOUT", 0.01)
    monkeypatch.setattr(client_module, "RECONNECT_DELAY", 0)
    # Hold the level across start and stop: outside it the logger emits DEBUG.
    with caplog.at_level(logging.INFO, logger=__name__):
        await client.async_start()
        try:
            first.is_connected = False
            client._disconnected(cast(Any, first))
            await client._reconnect_loop()
            assert established == [first, *silent, second]
            assert client.state.authenticated
        finally:
            await client.async_stop()

    assert caplog.record_tuples == [
        (
            __name__,
            logging.INFO,
            "Besen ACP#Garage is unavailable: Bluetooth connection lost",
        ),
        (__name__, logging.INFO, "Besen ACP#Garage is available again"),
    ]


async def test_rejected_reconnect_does_not_log_recovery_or_repeat_outage(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Repeated PIN rejections do not imply recovery or repeat outage errors."""

    first = _FakeBleakClient(_login_packets())
    rejected = [
        _FakeBleakClient([_evse_packet(1, _login_data()), _evse_packet(341)])
        for _ in range(2)
    ]
    client, _ = _client_with_connections([first, *rejected], monkeypatch)
    monkeypatch.setattr(client, "_schedule_reconnect", lambda: None)
    monkeypatch.setattr(client_module, "RECONNECT_DELAY", 0)
    # Hold the level across start and stop: outside it the logger emits DEBUG.
    with caplog.at_level(logging.INFO, logger=__name__):
        await client.async_start()
        try:
            first.is_connected = False
            client._disconnected(cast(Any, first))
            await client._reconnect_loop()
            await client._reconnect_loop()
            assert not client.state.authenticated
            assert not client.state.available
        finally:
            await client.async_stop()

    assert caplog.record_tuples == [
        (
            __name__,
            logging.INFO,
            "Besen ACP#Garage is unavailable: Bluetooth connection lost",
        ),
    ]
    assert "123456" not in caplog.text


@pytest.mark.parametrize("outage_before_stop", [False, True])
async def test_stop_and_restart_do_not_log_spurious_transitions(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    outage_before_stop: bool,
) -> None:
    """Shutdown is not an outage and clears any previous outage before restart."""

    first = _FakeBleakClient(_login_packets())
    second = _FakeBleakClient(_login_packets())
    client, _ = _client_with_connections([first, second], monkeypatch)
    try:
        with caplog.at_level(logging.INFO, logger=__name__):
            await client.async_start()
            if outage_before_stop:
                client._set_state(
                    available=False,
                    authenticated=False,
                    last_error="Bluetooth connection lost",
                )
            await client.async_stop()
            await client.async_start()
            await client.async_stop()
    finally:
        await client.async_stop()

    expected = (
        [
            (
                __name__,
                logging.INFO,
                "Besen ACP#Garage is unavailable: Bluetooth connection lost",
            )
        ]
        if outage_before_stop
        else []
    )
    assert caplog.record_tuples == expected


@pytest.mark.parametrize("result", ["success", "invalid_auth", "no_path"])
async def test_initial_setup_does_not_log_runtime_outage(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    result: str,
) -> None:
    """Initial connection success/failure is not a runtime outage/recovery pair."""

    packets = (
        [_evse_packet(1, _login_data()), _evse_packet(341)]
        if result == "invalid_auth"
        else _login_packets()
    )
    client = _client(_FakeBleakClient(packets), monkeypatch)
    if result == "no_path":
        monkeypatch.setattr(client, "_ble_device_provider", lambda: None)
    try:
        with caplog.at_level(logging.INFO, logger=__name__):
            if result == "success":
                await client.async_start()
            else:
                with pytest.raises(
                    InvalidAuth if result == "invalid_auth" else CannotConnect
                ):
                    await client.async_start()
            await client.async_stop()
    finally:
        await client.async_stop()
    assert not caplog.records


async def test_write_failures_log_one_outage(
    charging_client: tuple[BesenClient, _FakeBleakClient],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Transport failures report one outage without changing command exceptions."""

    client, fake = charging_client
    fake.fail_write = True
    with caplog.at_level(logging.INFO, logger=__name__):
        for _ in range(2):
            with pytest.raises(CommandFailed, match="Failed to send set_output_amps"):
                await client.async_set_charge_amps(16)

    assert caplog.record_tuples == [
        (
            __name__,
            logging.INFO,
            "Besen ACP#Garage is unavailable: "
            "Failed to send set_output_amps: write failed",
        ),
    ]


async def test_heartbeat_failure_does_not_duplicate_outage_log(
    charging_client: tuple[BesenClient, _FakeBleakClient],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Background heartbeat failures do not duplicate the outage report."""

    client, fake = charging_client
    fake.fail_write = True
    with caplog.at_level(logging.INFO, logger=__name__):
        client._notification(1, bytearray(_evse_packet(3)))
        pending = set(client._background_tasks)
        assert pending
        await asyncio.gather(*pending, return_exceptions=True)

    assert not client._background_tasks
    assert caplog.record_tuples == [
        (
            __name__,
            logging.INFO,
            "Besen ACP#Garage is unavailable: Failed to send heartbeat: write failed",
        ),
    ]


@pytest.mark.parametrize(
    ("error", "level"),
    [
        (CommandFailed("Failed to send heartbeat"), logging.DEBUG),
        (RuntimeError("unexpected failure"), logging.WARNING),
    ],
)
async def test_packet_handler_failure_log_level(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    level: int,
) -> None:
    """Expected transport failures are debug; unexpected errors stay visible."""

    client = _client(_FakeBleakClient([]), monkeypatch)

    async def _fail() -> None:
        raise error

    task = asyncio.create_task(_fail())
    client._background_tasks.add(task)
    with pytest.raises(type(error)):
        await task
    with caplog.at_level(logging.DEBUG, logger=__name__):
        client._background_task_done(task)

    assert not client._background_tasks
    assert caplog.record_tuples == [
        (__name__, level, f"Besen packet handler failed: {error}"),
    ]
