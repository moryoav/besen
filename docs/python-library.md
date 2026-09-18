# Besen Python library

`besen` is an async Python client for Besen EV chargers over Bluetooth Low Energy.
It provides connection management, PIN authentication, protocol parsing, typed
state models, and charger commands. The library lives in `src/besen`; the Home
Assistant integration is a separate consumer in `custom_components/besen`.

For Home Assistant installation, including the choice between the built-in and
HACS versions, see the [project README](../README.md#installation). Home Assistant
installs the required library automatically.

## Installation

For standalone Python applications:

```bash
pip install besen
```

Python 3.12 or newer is required. The library has been verified with a Besen BS20.
Other Besen chargers advertising as `ACP#...` and using the same BLE protocol may
also work.

## Basic usage

Applications provide the BLE device lookup function. This keeps discovery policy
outside the library, so callers can use `bleak`, Home Assistant Bluetooth helpers,
or another BLE stack integration.

Replace the example address and PIN with your charger's values. This example
observes state updates for one minute; it does not start or stop charging.
Disconnect other apps or bridges from the charger before running it.

```python
import asyncio
import logging

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from besen import BesenClient, BesenData

ADDRESS = "AA:BB:CC:DD:EE:FF"
PIN = "123456"


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("besen")

    device = await BleakScanner.find_device_by_address(ADDRESS, timeout=10.0)
    if device is None:
        raise RuntimeError("Charger was not found")

    def device_provider() -> BLEDevice | None:
        return device

    client = BesenClient(
        address=ADDRESS,
        pin=PIN,
        ble_device_provider=device_provider,
        logger=logger,
    )

    def handle_update(data: BesenData) -> None:
        print(
            "available=",
            data.available,
            "charging=",
            data.charge.charger_status,
            "power_w=",
            data.charge.power,
            "session_kwh=",
            data.charge.session_energy,
        )

    remove_listener = client.add_listener(handle_update)

    try:
        await client.async_start()
        await asyncio.sleep(60)
    finally:
        remove_listener()
        await client.async_stop()


asyncio.run(main())
```

## Client API

Create one `BesenClient` per charger:

```python
client = BesenClient(
    address="AA:BB:CC:DD:EE:FF",
    pin="123456",
    ble_device_provider=device_provider,
    logger=logger,
    advertised_name="ACP#Garage",
    sync_clock=True,
)
```

The BLE device provider is called before connection attempts and reconnects. It
must return a connectable `bleak.backends.device.BLEDevice` or `None` when no
connectable path is available.

### Lifecycle and state

- `await client.async_start()` connects, subscribes to notifications, and completes
  the charger login flow.
- `await client.async_stop()` cancels background tasks and disconnects.
- `client.add_listener(callback)` registers a synchronous state callback and
  returns a function that removes it.
- `client.state` returns the latest `BesenData` snapshot.
- `client.is_connected` reports whether the underlying BLE connection is open.

### Control methods

These methods can change the charger or operate real charging hardware. Test them
manually with appropriate supervision before using them in an automation.

- `await client.async_start_charging(amps=None)`
- `await client.async_stop_charging()`
- `await client.async_set_charge_amps(amps)`
- `await client.async_refresh_charge_amps()`
- `await client.async_set_lcd_brightness(brightness)`
- `await client.async_set_temperature_unit(unit)`
- `await client.async_set_language(language)`
- `await client.async_set_device_name(name)`
- `await client.async_refresh_config()`

Not every library control is exposed as a Home Assistant entity. See the
[README feature list](../README.md#features) for the integration's capabilities.

## State model

State updates are immutable dataclasses. Every listener receives a full `BesenData`
snapshot.

Important fields:

- `BesenData.available`: whether the latest BLE state is usable.
- `BesenData.authenticated`: whether the PIN login flow completed.
- `BesenData.info`: charger metadata such as serial, model, phases, firmware, and
  board revision.
- `BesenData.config`: configuration values such as charge amps, device name,
  language, temperature unit, LCD brightness, and RSSI.
- `BesenData.charge`: live charging state such as voltage, current, energy,
  temperature, plug state, output state, and charger status.
- `BesenData.last_command`: last parsed command response.
- `BesenData.last_error`: last connection, protocol, or command error string.

Important telemetry fields:

- `BesenData.charge.power`: charger-reported charging power in watts.
- `BesenData.charge.total_energy`: lifetime energy counter in kWh.
- `BesenData.charge.session_energy`: energy delivered during the current or most
  recently completed charging session in kWh.
- `BesenData.charge.inner_temp_c` and `BesenData.charge.outer_temp`: temperatures
  in Celsius, or `None` when the charger reports an invalid value.
- `BesenData.charge.l1_voltage`, `l2_voltage`, and `l3_voltage`: phase voltages in
  volts. L2 and L3 are populated only when the charger sends three-phase data.
- `BesenData.charge.l1_amperage`, `l2_amperage`, and `l3_amperage`: phase currents
  in amperes. L2 and L3 are populated only when the charger sends three-phase data.

## Exceptions

All library-specific errors inherit from `BesenError`.

- `CannotConnect`: the charger could not be reached or login timed out.
- `NoConnectablePath`: no active BLE path is available.
- `InvalidAuth`: the charger rejected the configured PIN.
- `ProtocolError`: malformed charger data was received.
- `CommandFailed`: a charger command could not be sent, was invalid, or a
  start-charging request was rejected or could not be confirmed.

`async_start_charging()` waits up to 10 seconds for the charger response, including
the Bluetooth write. A response with a charging or reservation error raises
`CommandFailed`. A successful response confirms the request, while actual charging
state continues to arrive through notifications.

If the response times out, the charging outcome is unknown. The client disconnects
and reconnects without automatically sending another start request. Cancellation
after sending also retires that Bluetooth session so a late reply cannot be
mistaken for the next request's response. Connection cleanup can extend the time
before the method exits. Concurrent start requests wait their turn before the
10-second timeout begins. Other command methods retain their existing behavior.

## Bluetooth notes

Besen chargers normally allow only one active BLE client connection. Stop other
tools or apps that may already be connected to the charger before starting this
client.

The client keeps one active BLE connection open, listens for notifications, replies
to heartbeats, and schedules reconnects when notifications stop. The caller remains
responsible for device discovery, adapter/proxy selection, and deciding when to
start or stop the client.

## Safety and attribution

This library is not a safety controller. Keep hardware protections, wiring, and
current limits appropriate for the installation independently of the software.

The Python library is MIT-licensed, with protocol work based on
[slespersen/evseMQTT](https://github.com/slespersen/evseMQTT). See
[LICENSE](../LICENSE) and [NOTICE.md](../NOTICE.md). The Core-derived Home Assistant
integration and tests use Apache 2.0; their license is separate from this library.
