# besen

[![release][release-badge]][release-url] [![CI][ci-badge]][ci-url] [![license][license-badge]][license-url]

`besen` is an async Python client for Besen EV chargers over Bluetooth Low Energy.
It provides the BLE connection management, login flow, protocol parsing, typed state
models, and charger control commands needed by applications such as Home Assistant
integrations.

The library has been verified with a Besen BS20 charger. Other Besen chargers that
advertise as `ACP#...` and use the same BLE protocol may also work.

## Installation

```bash
pip install besen
```

Python 3.12 or newer is required.

## Basic Usage

Applications provide the BLE device lookup function. This keeps discovery policy
outside the library, so callers can use `bleak`, Home Assistant Bluetooth helpers,
or another BLE stack integration.

```python
import asyncio
import logging

from bleak import BleakScanner

from besen import BesenClient, BesenData

ADDRESS = "AA:BB:CC:DD:EE:FF"
PIN = "123456"


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("besen")

    device = await BleakScanner.find_device_by_address(ADDRESS, timeout=10.0)
    if device is None:
        raise RuntimeError("Charger was not found")

    def device_provider():
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
            "amps=",
            data.config.charge_amps,
        )

    remove_listener = client.add_listener(handle_update)

    try:
        await client.async_start()
        await client.async_start_charging(amps=8)
        await asyncio.sleep(5)
        await client.async_stop_charging()
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

Lifecycle methods:

- `await client.async_start()` connects, subscribes to notifications, and completes
  the charger login flow.
- `await client.async_stop()` cancels background tasks and disconnects.
- `client.add_listener(callback)` registers a synchronous state callback and
  returns a function that removes it.
- `client.state` returns the latest `BesenData` snapshot.
- `client.is_connected` reports whether the underlying BLE connection is open.

Control methods:

- `await client.async_start_charging(amps=None)`
- `await client.async_stop_charging()`
- `await client.async_set_charge_amps(amps)`
- `await client.async_refresh_charge_amps()`
- `await client.async_set_lcd_brightness(brightness)`
- `await client.async_set_temperature_unit(unit)`
- `await client.async_set_language(language)`
- `await client.async_set_device_name(name)`
- `await client.async_refresh_config()`

## State Model

State updates are immutable dataclasses. Every listener receives a full `BesenData`
snapshot.

Important fields:

- `BesenData.available`: whether the latest BLE state is usable.
- `BesenData.authenticated`: whether the PIN login flow completed.
- `BesenData.info`: charger metadata such as serial, model, phases, firmware, and
  board revision.
- `BesenData.config`: configuration values such as charge amps, device name,
  language, temperature unit, LCD brightness, and RSSI.
- `BesenData.charge`: live charging state such as voltage, amperage, energy,
  temperature, plug state, output state, and charger status.
- `BesenData.last_command`: last parsed command response.
- `BesenData.last_error`: last connection, protocol, or command error string.

## Exceptions

All library-specific errors inherit from `BesenError`.

- `CannotConnect`: the charger could not be reached or login timed out.
- `NoConnectablePath`: no active BLE path is available.
- `InvalidAuth`: the charger rejected the configured PIN.
- `ProtocolError`: malformed charger data was received.
- `CommandFailed`: a charger command could not be sent or was invalid.

## Bluetooth Notes

Besen chargers normally allow only one active BLE client connection. Stop other
tools or apps that may already be connected to the charger before starting this
client.

The client keeps one active BLE connection open, listens for notifications, replies
to heartbeats, and schedules reconnects when notifications stop. The caller remains
responsible for device discovery, adapter/proxy selection, and deciding when to
start or stop the client.

## Home Assistant

This package is the reusable Python communication library used by the Besen Home
Assistant integration. Home Assistant user-facing setup and troubleshooting notes
are kept separately in [docs/home-assistant-custom-integration.md](docs/home-assistant-custom-integration.md).

## Safety

EV charging equipment controls real electrical hardware. This library is not a
safety controller. Keep charger hardware, breaker sizing, wiring, and local
electrical code protections correct independently of any software using this
package. Use conservative defaults and manual supervision when automating charging.

## Attribution

The Bluetooth protocol implementation is based on the MIT-licensed work in
[slespersen/evseMQTT](https://github.com/slespersen/evseMQTT), with MQTT-specific
runtime behavior replaced by a reusable async Python client.

Additional attribution details are maintained in [NOTICE.md](NOTICE.md).

## License

MIT. See [LICENSE](LICENSE).

[release-badge]: https://img.shields.io/github/v/release/moryoav/ha_besen?style=flat-square
[release-url]: https://github.com/moryoav/ha_besen/releases
[ci-badge]: https://img.shields.io/github/actions/workflow/status/moryoav/ha_besen/ci.yml?branch=main&style=flat-square&label=CI
[ci-url]: https://github.com/moryoav/ha_besen/actions/workflows/ci.yml
[license-badge]: https://img.shields.io/github/license/moryoav/ha_besen?style=flat-square
[license-url]: https://github.com/moryoav/ha_besen/blob/main/LICENSE
