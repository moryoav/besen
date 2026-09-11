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
    CLOCK_SYNC_INTERVAL,
    CONNECT_ATTEMPTS,
    CONNECT_TIMEOUT,
    DEFAULT_CHARGE_AMPS,
    DISCONNECT_TIMEOUT,
    FALLBACK_MAX_CHARGE_AMPS,
    LANGUAGES,
    LOGIN_ATTEMPTS,
    LOGIN_REQUEST_RETRY_INTERVAL,
    LOGIN_TIMEOUT,
    MESSAGE_TIMEOUT,
    MIN_CHARGE_AMPS,
    NEW_BOARD_READ_UUID,
    NEW_BOARD_WRITE_UUID,
    READ_UUID,
    RECONNECT_DELAY,
    REV_READ_UUID,
    REV_WRITE_UUID,
    SILENT_LOGIN_TIMEOUT,
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
        self._connect_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._packet_lock = asyncio.Lock()
        self._ready_event = asyncio.Event()
        self._connect_owner_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._stopping = False
        self._auth_failed = False
        self._connection_error: str | None = None
        self._received_any_packet = False
        self._login_request_sent = False
        self._last_login_request: float | None = None
        self._login_confirm_sent = False
        self._connection_generation = 0
        self._disconnecting_client: BleakClientWithServiceCache | None = None
        self._reconnect_requested = False
        self._last_message = time.monotonic()
        self._last_clock_sync: float | None = None
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
        try:
            await self._connect_and_login()
        except BaseException:
            self._reconnect_requested = False
            try:
                await asyncio.shield(self._disconnect_client())
            except CannotConnect as err:
                self._logger.warning(
                    "Unable to release BLE connection after startup failure: %s",
                    err,
                )
            self._set_state(available=False, authenticated=False)
            raise
        self._start_watchdog()

    async def async_stop(self) -> None:
        """Stop tasks and disconnect from the charger."""

        self._stopping = True
        self._ready_event.set()
        current = asyncio.current_task()
        tasks = {
            task
            for task in (
                self._connect_owner_task,
                self._reconnect_task,
                self._watchdog_task,
            )
            if task is not None and task is not current
        }
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        await self._cancel_background_tasks()
        self._connect_owner_task = None
        self._reconnect_task = None
        self._watchdog_task = None
        self._reconnect_requested = False
        disconnect_error: CannotConnect | None = None
        for _attempt in range(2):
            try:
                await self._disconnect_client()
            except CannotConnect as err:
                disconnect_error = err
                continue
            disconnect_error = None
            break
        if disconnect_error is not None:
            self._logger.error(
                "Besen BLE cleanup failed during shutdown: %s", disconnect_error
            )
        self._set_state(
            available=False,
            authenticated=False,
            last_error=str(disconnect_error) if disconnect_error else None,
        )

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
        self._set_state(config=self._state.config.updated(lcd_brightness=value))

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
        self._set_state(config=self._state.config.updated(temperature_unit=unit))

    async def async_set_language(self, language: str) -> None:
        """Set the app language stored on the charger."""

        if language not in LANGUAGES:
            raise CommandFailed(f"Unsupported language: {language}")
        await self._send_command(
            33039,
            [1, LANGUAGES[language]],
            name="set_language",
        )
        self._set_state(config=self._state.config.updated(language=language))

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
        await self._async_sync_clock_if_due(force=True)
        await self._send_command(33025, [2, 0], name="get_time")

    async def _connect_and_login(self) -> None:
        """Connect to the BLE device and wait for authentication."""

        owner = asyncio.current_task()
        assert owner is not None
        async with self._connect_lock:
            self._connect_owner_task = owner
            try:
                if self._stopping:
                    raise CannotConnect("Besen client is stopping")
                await self._connect_and_login_locked()
                if not self.is_connected or not self._state.authenticated:
                    raise CannotConnect("Charger login ended without an active session")
            finally:
                if self._connect_owner_task is owner:
                    self._connect_owner_task = None

    async def _connect_and_login_locked(self) -> None:
        """Own the single connection/login workflow until it completes."""

        for attempt in range(1, LOGIN_ATTEMPTS + 1):
            if self._stopping:
                raise CannotConnect("Besen client is stopping")
            self._ready_event = asyncio.Event()
            self._auth_failed = False
            self._connection_error = None
            self._received_any_packet = False
            await self._connect_once()
            timed_out = False
            try:
                async with asyncio.timeout(SILENT_LOGIN_TIMEOUT):
                    await self._ready_event.wait()
            except TimeoutError:
                if self._received_any_packet:
                    try:
                        async with asyncio.timeout(
                            LOGIN_TIMEOUT - SILENT_LOGIN_TIMEOUT
                        ):
                            await self._ready_event.wait()
                    except TimeoutError:
                        timed_out = True
                else:
                    timed_out = True
            if self._auth_failed:
                try:
                    await self._disconnect_login_attempt(
                        "The charger rejected the configured PIN"
                    )
                except CannotConnect as err:
                    self._logger.warning(
                        "Unable to release BLE connection after PIN rejection: %s",
                        err,
                    )
                raise InvalidAuth("The charger rejected the configured PIN")

            if (
                not timed_out
                and self._connection_error is None
                and self.is_connected
                and self._state.authenticated
            ):
                self._reconnect_requested = False
                return

            reason = self._connection_error or "Timed out waiting for charger login"
            await self._disconnect_login_attempt(reason)
            if (timed_out and self._received_any_packet) or attempt == LOGIN_ATTEMPTS:
                raise CannotConnect(reason)
            if self._received_any_packet:
                message = "Besen login did not complete"
            else:
                message = "No Besen packets were received during login"
            self._logger.warning(
                "%s; retrying a fresh Bluetooth connection in %s seconds "
                "(attempt %s/%s)",
                message,
                RECONNECT_DELAY,
                attempt,
                LOGIN_ATTEMPTS,
            )
            await asyncio.sleep(RECONNECT_DELAY)

    async def _disconnect_login_attempt(self, reason: str) -> None:
        """Disconnect an incomplete login attempt before it can occupy a slot."""

        self._set_state(
            available=False,
            authenticated=False,
            last_error=reason,
        )
        await self._disconnect_client()

    async def _connect_once(self) -> None:
        """Open a BLE connection and subscribe to notifications."""

        if self._stopping:
            raise CannotConnect("Besen client is stopping")
        ble_device = self._ble_device_provider()
        if ble_device is None:
            raise CannotConnect("No connectable Bluetooth path is available")

        await self._disconnect_client()
        self._assembler = PacketAssembler()
        self._login_request_sent = False
        self._last_login_request = None
        self._login_confirm_sent = False
        generation = self._connection_generation
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
            client = self._client
            if self._stopping:
                raise CannotConnect("Besen client stopped while connecting")
            self._characteristics = self._select_characteristics()
            self._logger.debug(
                "Selected Besen %s board characteristics read=%s write=%s "
                "write_with_response=%s",
                self._characteristics.board_revision.value,
                self._characteristics.read_uuid,
                self._characteristics.write_uuid,
                self._characteristics.write_with_response,
            )
            self._update_info(board_revision=self._characteristics.board_revision)
            self._last_message = time.monotonic()
            self._last_unavailable_log = None
            self._set_state(available=True, authenticated=False, last_error=None)

            def _handle_notification(sender: Any, data: bytearray) -> None:
                self._notification(sender, data, generation=generation)

            await self._client.start_notify(
                self._characteristics.read_uuid,
                _handle_notification,
            )
            if self._client is not client or not client.is_connected:
                raise CannotConnect(
                    "Charger disconnected while notifications were starting"
                )
        except Exception as err:
            await self._disconnect_client()
            raise CannotConnect(
                f"Unable to connect to charger via BLE: {type(err).__name__}: {err}"
            ) from err

    async def _disconnect_client(self) -> None:
        """Disconnect the BLE client if connected."""

        client = self._client
        self._connection_generation += 1
        if client is None:
            self._characteristics = None
            return
        read_uuid = self._characteristics.read_uuid if self._characteristics else None
        self._disconnecting_client = client
        disconnect_error: Exception | None = None
        try:
            await self._cancel_background_tasks()
            async with self._command_lock:
                if client.is_connected and read_uuid:
                    try:
                        async with asyncio.timeout(DISCONNECT_TIMEOUT):
                            await client.stop_notify(read_uuid)
                    except Exception as err:
                        self._logger.debug(
                            "Unable to stop Besen notifications: %s", err
                        )
                if client.is_connected:
                    try:
                        async with asyncio.timeout(DISCONNECT_TIMEOUT):
                            await client.disconnect()
                    except Exception as err:
                        disconnect_error = err
                if not client.is_connected and self._client is client:
                    self._client = None
                    self._characteristics = None
        finally:
            self._disconnecting_client = None
            if not client.is_connected and self._client is client:
                self._client = None
                self._characteristics = None

        if client.is_connected:
            message = "Unable to release the existing Besen BLE connection"
            self._logger.warning(
                "%s: %s", message, disconnect_error or "still connected"
            )
            raise CannotConnect(message) from disconnect_error

    async def _cancel_background_tasks(self) -> None:
        """Cancel packet handlers that belong to an ending connection."""

        current = asyncio.current_task()
        tasks = [task for task in self._background_tasks if task is not current]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._background_tasks.difference_update(tasks)

    def _background_task_done(self, task: asyncio.Task[None]) -> None:
        """Consume packet-handler failures so they are not lost by asyncio."""

        self._background_tasks.discard(task)
        if task.cancelled():
            return
        if err := task.exception():
            self._logger.warning("Besen packet handler failed: %s", err)

    def _select_characteristics(self) -> CharacteristicPair:
        """Select a usable known UUID pair and its supported GATT write mode."""

        assert self._client is not None
        services = self._client.services
        for read_uuid, write_uuid, revision in (
            (NEW_BOARD_READ_UUID, NEW_BOARD_WRITE_UUID, BoardRevision.NEW),
            (REV_READ_UUID, REV_WRITE_UUID, BoardRevision.REVISED),
            (READ_UUID, WRITE_UUID, BoardRevision.OLD),
        ):
            read = services.get_characteristic(read_uuid)
            write = services.get_characteristic(write_uuid)
            if read is None or write is None:
                continue
            if not {"notify", "indicate"}.intersection(read.properties):
                continue
            if not {"write", "write-without-response"}.intersection(write.properties):
                continue
            return CharacteristicPair(
                read_uuid=read_uuid,
                write_uuid=write_uuid,
                board_revision=revision,
                # Preserve the existing mode where supported. Some BS20 variants
                # expose only acknowledged writes on FFF2.
                write_with_response="write-without-response" not in write.properties,
            )

        self._logger.debug(
            "Discovered Besen GATT services and characteristics: %s",
            [
                (
                    service.uuid,
                    [(char.uuid, char.properties) for char in service.characteristics],
                )
                for service in services
            ],
        )
        raise CannotConnect(
            "No supported Besen GATT characteristic pair found. "
            "Expected FFE4/FFE9, CDD1/CDD2, or FFF1/FFF2 with "
            "notification and write support; see debug logs for discovered services."
        )

    def _disconnected(self, client: BleakClientWithServiceCache) -> None:
        """Handle an unexpected BLE disconnection."""

        if (
            self._stopping
            or client is self._disconnecting_client
            or client is not self._client
        ):
            return
        self._client = None
        self._characteristics = None
        self._connection_generation += 1
        for task in self._background_tasks:
            task.cancel()
        self._set_state(
            available=False,
            authenticated=False,
            last_error="Bluetooth connection lost",
        )
        self._connection_error = "Bluetooth connection lost during charger login"
        self._ready_event.set()
        self._schedule_reconnect()

    def _notification(
        self,
        _sender: Any,
        data: bytearray,
        *,
        generation: int | None = None,
    ) -> None:
        """Process a BLE notification callback."""

        if generation is not None and generation != self._connection_generation:
            return
        self._last_message = time.monotonic()
        try:
            packets = self._assembler.feed(data)
        except ProtocolError as err:
            self._logger.debug("Dropping invalid packet: %s", err)
            return
        for packet in packets:
            self._received_any_packet = True
            task = asyncio.create_task(
                self._async_handle_packet(
                    packet.command,
                    packet.data,
                    packet.identifier,
                    generation=generation,
                )
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_task_done)

    async def _async_handle_packet(
        self,
        command: int,
        data: bytes,
        identifier: str,
        *,
        generation: int | None = None,
    ) -> None:
        """Handle a parsed charger packet."""

        async with self._packet_lock:
            if self._stopping or (
                generation is not None and generation != self._connection_generation
            ):
                return
            await self._async_handle_packet_locked(command, data, identifier)

    async def _async_handle_packet_locked(
        self,
        command: int,
        data: bytes,
        identifier: str,
    ) -> None:
        """Handle one packet in connection order."""

        self._logger.debug("Received Besen command %s", command)
        if command == 341:
            if not self._login_request_sent or self._state.authenticated:
                self._logger.debug("Ignoring unsolicited Besen login rejection")
                return
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
            if self._state.authenticated:
                return
            now = time.monotonic()
            if (
                self._last_login_request is not None
                and now - self._last_login_request < LOGIN_REQUEST_RETRY_INTERVAL
            ):
                return
            self._last_login_request = now
            try:
                await self._send_login_request()
            except Exception:
                self._last_login_request = None
                raise
            self._login_request_sent = True
            return

        if command == 2:
            self._update_info(**values)
            if not self._login_request_sent:
                self._logger.debug(
                    "Deferring Besen login confirmation until this connection "
                    "has sent a login request"
                )
                return
            if self._state.authenticated or self._login_confirm_sent:
                return
            self._login_confirm_sent = True
            try:
                await self._send_login_confirm()
            except Exception:
                self._login_confirm_sent = False
                raise
            await self.async_refresh_config()
            self._set_state(available=True, authenticated=True, last_error=None)
            self._ready_event.set()
            return

        if command == 3:
            if not self._state.authenticated or self._state.info.serial is None:
                self._logger.debug("Deferring Besen heartbeat until login is complete")
                return
            await self._send_heartbeat()
            if self._state.authenticated:
                await self._async_sync_clock_if_due()
            return

        if command in (4, 5, 6, 13):
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

    async def _async_sync_clock_if_due(self, *, force: bool = False) -> None:
        """Sync the charger clock once per login and then at a bounded rate."""

        if not self.sync_clock:
            return
        now = time.monotonic()
        if (
            not force
            and self._last_clock_sync is not None
            and now - self._last_clock_sync < CLOCK_SYNC_INTERVAL
        ):
            return
        await self._send_command(33025, [1, timestamp_bytes()], name="set_time")
        self._last_clock_sync = now

    async def _send_command(
        self,
        command: int,
        payload: list[Any] | None,
        *,
        name: str,
    ) -> None:
        """Build and send a command packet."""

        async with self._command_lock:
            client = self._client
            characteristics = self._characteristics
            generation = self._connection_generation
            if client is None or characteristics is None or not client.is_connected:
                raise CommandFailed("Charger is not connected")
            serial = self._state.info.serial
            if serial is None:
                raise CommandFailed("Charger serial is not known yet")
            packet = build_command(serial, self.pin, command, payload)
            try:
                await client.write_gatt_char(
                    characteristics.write_uuid,
                    packet,
                    response=characteristics.write_with_response,
                )
            except Exception as err:
                if client is self._client and generation == self._connection_generation:
                    self._set_state(
                        available=False,
                        authenticated=False,
                        last_error=f"Failed to send {name}: {err}",
                    )
                    self._connection_error = f"Failed to send {name}: {err}"
                    self._ready_event.set()
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
        self._reconnect_requested = True
        if self._connect_lock.locked():
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_requested = False
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Reconnect until successful or stopped."""

        while not self._stopping:
            await asyncio.sleep(RECONNECT_DELAY)
            self._reconnect_requested = False
            try:
                await self._connect_and_login()
            except InvalidAuth:
                self._logger.error("Besen PIN rejected during reconnect")
                return
            except CannotConnect as err:
                self._logger.debug("Besen reconnect failed: %s", err)
            else:
                if (
                    self._reconnect_requested
                    or not self.is_connected
                    or not self._state.authenticated
                ):
                    continue
                self._logger.info("Besen reconnected")
                return

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
