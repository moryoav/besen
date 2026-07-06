"""Async BLE client for Besen chargers."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any, cast

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .const import (
    CONNECT_ATTEMPTS,
    CONNECT_TIMEOUT,
    DEFAULT_CHARGE_AMPS,
    FALLBACK_MAX_CHARGE_AMPS,
    LANGUAGES,
    LOGIN_TIMEOUT,
    MESSAGE_TIMEOUT,
    MIN_CHARGE_AMPS,
    NEW_BOARD_READ_UUID,
    NEW_BOARD_SERVICE_PREFIXES,
    NEW_BOARD_WRITE_UUID,
    READ_UUID,
    RECONNECT_DELAY,
    REV_BOARD_SERVICE_PREFIXES,
    REV_READ_UUID,
    REV_WRITE_UUID,
    STOP_REASON,
    TEMPERATURE_UNIT_ALIASES,
    TEMPERATURE_UNITS,
    WRITE_UUID,
)
from .exceptions import CannotConnect, CommandFailed, InvalidAuth, ProtocolError
from .models import (
    BesenData,
    BoardRevision,
    CharacteristicPair,
    ChargerInfo,
    CommandResult,
)
from .protocol import (
    PARSERS,
    PacketAssembler,
    build_command,
    device_name_bytes,
    generate_charge_id,
    timestamp_bytes,
)

BLEDeviceProvider = Callable[[], BLEDevice | None]
StateListener = Callable[[BesenData], None]

USER_ID = [101, 118, 115, 101, 77, 81, 84, 84, 0, 0, 0, 0, 0, 0, 0, 0]
UNAVAILABLE_LOG_INTERVAL_SECONDS = 600


class BesenClient:
    """Manage a Besen charger BLE connection."""

    def __init__(
        self,
        *,
        address: str,
        pin: str,
        ble_device_provider: BLEDeviceProvider,
        logger: logging.Logger,
        advertised_name: str | None = None,
        sync_clock: bool = True,
    ) -> None:
        self.address = address
        self.pin = pin
        self.sync_clock = sync_clock
        self._ble_device_provider = ble_device_provider
        self._logger = logger
        self._name = advertised_name or address
        self._client: BleakClientWithServiceCache | None = None
        self._characteristics: CharacteristicPair | None = None
        self._assembler = PacketAssembler()
        self._listeners: set[StateListener] = set()
        self._command_lock = asyncio.Lock()
        self._ready_event = asyncio.Event()
        self._reconnect_task: asyncio.Task[None] | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._stopping = False
        self._reconnecting = False
        self._auth_failed = False
        self._last_message = time.monotonic()
        self._last_unavailable_log: float | None = None
        self._state = BesenData(
            info=ChargerInfo(address=address, advertised_name=advertised_name)
        )

    @property
    def state(self) -> BesenData:
        """Return the latest charger state."""

        return self._state

    @property
    def is_connected(self) -> bool:
        """Return whether the BLE client is connected."""

        return bool(self._client and self._client.is_connected)

    def add_listener(self, listener: StateListener) -> Callable[[], None]:
        """Register a state listener."""

        self._listeners.add(listener)

        def _remove() -> None:
            self._listeners.discard(listener)

        return _remove

    async def async_start(self) -> None:
        """Connect and complete the charger login flow."""

        self._stopping = False
        await self._connect_and_login()
        self._start_watchdog()

    async def async_stop(self) -> None:
        """Stop tasks and disconnect from the charger."""

        self._stopping = True
        for task in (self._reconnect_task, self._watchdog_task):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        for task in self._background_tasks:
            task.cancel()
        for task in self._background_tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._background_tasks.clear()
        self._reconnect_task = None
        self._watchdog_task = None
        await self._disconnect_client()
        self._set_state(available=False, authenticated=False)

    async def async_start_charging(self, amps: int | None = None) -> None:
        """Start charging at the requested amperage."""

        await self._send_command(
            32775,
            self._charge_start_payload(self._clamp_amps(amps)),
            name="charge_start",
        )

    async def async_stop_charging(self) -> None:
        """Stop charging."""

        await self._send_command(
            32776,
            [1, USER_ID, *([0] * 30)],
            name="charge_stop",
        )

    async def async_set_charge_amps(self, amps: int) -> None:
        """Set the maximum charge amps."""

        clamped = self._clamp_amps(amps)
        await self._send_command(33031, [1, clamped], name="set_output_amps")
        await self.async_refresh_charge_amps()

    async def async_refresh_charge_amps(self) -> None:
        """Request the current charge amps from the charger."""

        await self._send_command(33031, [2, 0], name="get_output_amps")

    async def async_set_lcd_brightness(self, brightness: int) -> None:
        """Set LCD brightness percentage."""

        value = max(1, min(100, int(brightness)))
        await self._send_command(
            33122,
            [0, 2, value, 0, 0, 0, 0, 0],
            name="set_lcd_brightness",
        )

    async def async_set_temperature_unit(self, unit: str) -> None:
        """Set the charger temperature unit."""

        unit = TEMPERATURE_UNIT_ALIASES.get(unit, unit)
        if unit not in TEMPERATURE_UNITS:
            raise CommandFailed(f"Unsupported temperature unit: {unit}")
        await self._send_command(
            33042,
            [1, TEMPERATURE_UNITS[unit]],
            name="set_temperature_unit",
        )

    async def async_set_language(self, language: str) -> None:
        """Set the app language stored on the charger."""

        if language not in LANGUAGES:
            raise CommandFailed(f"Unsupported language: {language}")
        await self._send_command(
            33039,
            [1, LANGUAGES[language]],
            name="set_language",
        )

    async def async_set_device_name(self, name: str) -> None:
        """Set the charger's advertised name."""

        clean_name = name.strip()
        if not clean_name:
            raise CommandFailed("Device name cannot be empty")
        await self._send_command(
            33032,
            [1, device_name_bytes(clean_name)],
            name="set_device_name",
        )
        await self._send_command(33032, [2, 0], name="get_device_name")

    async def async_refresh_config(self) -> None:
        """Request configuration values from the charger."""

        await self._send_command(33042, [2, 0], name="get_temperature_unit")
        await self._send_command(33030, None, name="get_config_version")
        await self._send_command(33032, [2, 0], name="get_device_name")
        await self._send_command(33031, [2, 0], name="get_output_amps")
        await self._send_command(33039, [2, 0], name="get_language")
        await self._send_command(
            33122,
            [0, 1, 0, 1, 0, 0, 0, 0],
            name="get_lcd_brightness",
        )
        if self.sync_clock:
            await self._send_command(33025, [1, timestamp_bytes()], name="set_time")
        await self._send_command(33025, [2, 0], name="get_time")

    async def _connect_and_login(self) -> None:
        """Connect to the BLE device and wait for authentication."""

        self._ready_event = asyncio.Event()
        self._auth_failed = False
        await self._connect_once()
        try:
            async with asyncio.timeout(LOGIN_TIMEOUT):
                await self._ready_event.wait()
        except TimeoutError as err:
            raise CannotConnect("Timed out waiting for charger login") from err
        if self._auth_failed:
            raise InvalidAuth("The charger rejected the configured PIN")

    async def _connect_once(self) -> None:
        """Open a BLE connection and subscribe to notifications."""

        ble_device = self._ble_device_provider()
        if ble_device is None:
            raise CannotConnect("No connectable Bluetooth path is available")

        await self._disconnect_client()
        self._assembler = PacketAssembler()
        self._logger.debug("Connecting to Besen at %s", self.address)
        try:
            self._client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self._name,
                disconnected_callback=self._disconnected,
                max_attempts=CONNECT_ATTEMPTS,
                ble_device_callback=cast(
                    Callable[[], BLEDevice],
                    self._ble_device_provider,
                ),
                timeout=CONNECT_TIMEOUT,
            )
            self._characteristics = self._select_characteristics()
            self._logger.debug(
                "Selected Besen %s board characteristics read=%s write=%s",
                self._characteristics.board_revision.value,
                self._characteristics.read_uuid,
                self._characteristics.write_uuid,
            )
            self._update_info(board_revision=self._characteristics.board_revision)
            await self._client.start_notify(
                self._characteristics.read_uuid,
                self._notification,
            )
        except Exception as err:
            await self._disconnect_client()
            raise CannotConnect(
                f"Unable to connect to charger via BLE: {type(err).__name__}: {err}"
            ) from err

        self._last_message = time.monotonic()
        self._last_unavailable_log = None
        self._set_state(available=True, last_error=None)

    async def _disconnect_client(self) -> None:
        """Disconnect the BLE client if connected."""

        client = self._client
        self._client = None
        if client is None:
            return
        read_uuid = self._characteristics.read_uuid if self._characteristics else None
        if client.is_connected and read_uuid:
            with suppress(Exception):
                await client.stop_notify(read_uuid)
        if client.is_connected:
            with suppress(Exception):
                await client.disconnect()

    def _select_characteristics(self) -> CharacteristicPair:
        """Select read/write characteristics from advertised GATT services."""

        assert self._client is not None
        service_uuids = [service.uuid.lower() for service in self._client.services]
        if any(uuid.startswith(NEW_BOARD_SERVICE_PREFIXES) for uuid in service_uuids):
            return CharacteristicPair(
                read_uuid=NEW_BOARD_READ_UUID,
                write_uuid=NEW_BOARD_WRITE_UUID,
                board_revision=BoardRevision.NEW,
            )
        if any(uuid.startswith(REV_BOARD_SERVICE_PREFIXES) for uuid in service_uuids):
            return CharacteristicPair(
                read_uuid=REV_READ_UUID,
                write_uuid=REV_WRITE_UUID,
                board_revision=BoardRevision.REVISED,
            )
        return CharacteristicPair(
            read_uuid=READ_UUID,
            write_uuid=WRITE_UUID,
            board_revision=BoardRevision.OLD,
        )

    def _disconnected(self, _client: BleakClientWithServiceCache) -> None:
        """Handle an unexpected BLE disconnection."""

        if self._stopping or self._reconnecting:
            return
        self._set_state(
            available=False,
            authenticated=False,
            last_error="Bluetooth connection lost",
        )
        self._schedule_reconnect()

    def _notification(self, _sender: Any, data: bytearray) -> None:
        """Process a BLE notification callback."""

        self._last_message = time.monotonic()
        try:
            packets = self._assembler.feed(data)
        except ProtocolError as err:
            self._logger.debug("Dropping invalid packet: %s", err)
            return
        for packet in packets:
            task = asyncio.create_task(
                self._async_handle_packet(
                    packet.command,
                    packet.data,
                    packet.identifier,
                )
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def _async_handle_packet(
        self,
        command: int,
        data: bytes,
        identifier: str,
    ) -> None:
        """Handle a parsed charger packet."""

        self._logger.debug("Received Besen command %s", command)
        if command == 341:
            self._auth_failed = True
            self._ready_event.set()
            self._set_state(
                available=True,
                authenticated=False,
                last_error="The charger rejected the configured PIN",
            )
            return

        parser = PARSERS.get(command)
        values: dict[str, Any] = {}
        if parser is not None:
            try:
                values = parser(data, identifier)
            except (IndexError, UnicodeDecodeError, ProtocolError) as err:
                self._logger.debug("Failed to parse command %s: %s", command, err)
                return

        if command == 1:
            self._update_info(**values)
            await self._send_login_request()
            return

        if command == 2:
            self._update_info(**values)
            await self._send_login_confirm()
            self._set_state(available=True, authenticated=True, last_error=None)
            self._ready_event.set()
            await self.async_refresh_config()
            return

        if command == 3:
            await self._send_heartbeat()
            if self.sync_clock:
                await self._send_command(33025, [1, timestamp_bytes()], name="set_time")
            return

        if command in (4, 13):
            self._set_state(charge=self._state.charge.updated(**values))
            return

        if command == 262:
            self._update_info(**values)
            return

        if command in (257, 263, 264, 271, 274):
            self._set_state(config=self._state.config.updated(**values))
            return

        if command == 7:
            self._set_state(
                last_command=CommandResult(command="charge_start", values=values)
            )
            if values.get("error_reason") not in (None, "No error"):
                self._logger.warning("Charge start response: %s", values)
            return

        if command == 8:
            self._set_state(
                last_command=CommandResult(command="charge_stop", values=values)
            )
            if values.get("stop_result") not in (None, STOP_REASON.get(11)):
                self._logger.debug("Charge stop response: %s", values)

    async def _send_login_request(self) -> None:
        """Send login request."""

        await self._send_command(32770, None, name="login_request")

    async def _send_login_confirm(self) -> None:
        """Confirm login."""

        await self._send_command(32769, [1], name="login_confirm")

    async def _send_heartbeat(self) -> None:
        """Reply to charger heartbeat."""

        await self._send_command(32771, [1], name="heartbeat")

    async def _send_command(
        self,
        command: int,
        payload: list[Any] | None,
        *,
        name: str,
    ) -> None:
        """Build and send a command packet."""

        if (
            self._client is None
            or self._characteristics is None
            or not self.is_connected
        ):
            raise CommandFailed("Charger is not connected")
        serial = self._state.info.serial
        if serial is None:
            raise CommandFailed("Charger serial is not known yet")

        packet = build_command(serial, self.pin, command, payload)
        async with self._command_lock:
            try:
                await self._client.write_gatt_char(
                    self._characteristics.write_uuid,
                    packet,
                    response=False,
                )
            except Exception as err:
                self._set_state(
                    available=False,
                    last_error=f"Failed to send {name}: {err}",
                )
                self._schedule_reconnect()
                raise CommandFailed(f"Failed to send {name}") from err

    def _charge_start_payload(self, amps: int) -> list[Any]:
        """Build charge start payload."""

        line_id = 2 if self._state.info.phases == 3 else 1
        return [
            line_id,
            USER_ID,
            generate_charge_id(),
            0,
            timestamp_bytes(),
            1,
            1,
            [255, 255],
            [255, 255],
            [255, 255],
            amps,
        ]

    def _clamp_amps(self, amps: int | None) -> int:
        """Clamp amps to charger limits."""

        requested = int(
            amps
            or self._state.config.charge_amps
            or self._state.info.output_max_amps
            or DEFAULT_CHARGE_AMPS
        )
        max_amps = self._state.info.output_max_amps or FALLBACK_MAX_CHARGE_AMPS
        return max(MIN_CHARGE_AMPS, min(max_amps, requested))

    def _update_info(self, **values: Any) -> None:
        """Merge charger info values into state."""

        if not values:
            return
        if (
            self._state.info.board_revision == BoardRevision.REVISED
            and values.get("software_version") is None
            and values.get("hardware_version")
        ):
            values["software_version"] = values["hardware_version"]
        self._set_state(info=self._state.info.updated(**values))

    def _set_state(self, **changes: Any) -> None:
        """Update state and notify listeners."""

        self._state = self._state.updated(**changes)
        for listener in list(self._listeners):
            listener(self._state)

    def _start_watchdog(self) -> None:
        """Start notification inactivity watchdog."""

        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    async def _watchdog_loop(self) -> None:
        """Reconnect if notifications stop arriving."""

        while True:
            await asyncio.sleep(MESSAGE_TIMEOUT)
            if self._stopping:
                return
            if time.monotonic() - self._last_message <= MESSAGE_TIMEOUT:
                continue
            self._log_unavailable_warning(
                "No Besen notification received for %s seconds; reconnecting",
                MESSAGE_TIMEOUT,
            )
            self._set_state(
                available=False,
                authenticated=False,
                last_error="No notifications received; reconnecting",
            )
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        """Schedule a reconnect task if needed."""

        if self._stopping:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Reconnect until successful or stopped."""

        while not self._stopping:
            await asyncio.sleep(RECONNECT_DELAY)
            self._reconnecting = True
            try:
                await self._connect_and_login()
            except InvalidAuth:
                self._logger.error("Besen PIN rejected during reconnect")
                return
            except CannotConnect as err:
                self._logger.debug("Besen reconnect failed: %s", err)
            else:
                self._logger.info("Besen reconnected")
                return
            finally:
                self._reconnecting = False

    def _log_unavailable_warning(self, message: str, *args: object) -> None:
        """Log unavailable warnings without repeating every watchdog cycle."""

        now = time.monotonic()
        if (
            self._last_unavailable_log is not None
            and now - self._last_unavailable_log < UNAVAILABLE_LOG_INTERVAL_SECONDS
        ):
            return
        self._last_unavailable_log = now
        self._logger.warning(message, *args)
