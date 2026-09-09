# besen

[![release][release-badge]][release-url] [![CI][ci-badge]][ci-url] [![license][license-badge]][license-url]

`besen` is an async Python client for Besen EV chargers over Bluetooth Low Energy.
It provides the BLE connection management, login flow, protocol parsing, typed state
models, and charger control commands needed by applications such as Home Assistant
integrations.

## Home Assistant users

I maintain the full-feature Home Assistant custom integration in this repository,
alongside the Python library. Install **Besen** through HACS using
[`moryoav/besen`](https://my.home-assistant.io/redirect/hacs_repository/?owner=moryoav&repository=besen&category=integration),
then follow the [installation and upgrade guide](https://github.com/moryoav/besen/blob/main/docs/home-assistant-custom-integration.md).
Home Assistant installs the Python dependency automatically.

I develop both parts on `main` and publish stable `v*` releases for HACS and PyPI.
HACS offers the latest stable release when it refreshes the repository; installing
an update and restarting Home Assistant remain under the user's control.

The built-in Home Assistant integration has a separate release schedule and may
have fewer features. I submit selected changes to Core in focused pull requests;
those reviews do not delay releases of the full custom integration here.

As of September 9, 2026, the latest custom release is **0.4.3**. It includes the
sensor, switch, number, select, and text platforms, plus Bluetooth write-mode
compatibility for the single-phase BS20 variant reported in issue #1. It also
retries incomplete Bluetooth service discovery after attempting to clear the
device's service cache. The reporter confirmed setup and readings with 0.4.2;
charging control and the new discovery recovery still need hardware confirmation.

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
            "power_w=",
            data.charge.power,
            "session_kwh=",
            data.charge.session_energy,
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
are kept separately in
[docs/home-assistant-custom-integration.md](https://github.com/moryoav/besen/blob/main/docs/home-assistant-custom-integration.md).

## Safety

EV charging equipment controls real electrical hardware. This library is not a
safety controller. Keep charger hardware, breaker sizing, wiring, and local
electrical code protections correct independently of any software using this
package. Use conservative defaults and manual supervision when automating charging.

## Attribution

The Bluetooth protocol implementation is based on the MIT-licensed work in
[slespersen/evseMQTT](https://github.com/slespersen/evseMQTT), with MQTT-specific
runtime behavior replaced by a reusable async Python client.

Additional attribution details are maintained in
[NOTICE.md](https://github.com/moryoav/besen/blob/main/NOTICE.md).

## License

MIT. See [LICENSE](https://github.com/moryoav/besen/blob/main/LICENSE).

[release-badge]: https://img.shields.io/github/v/release/moryoav/besen?style=flat-square
[release-url]: https://github.com/moryoav/besen/releases
[ci-badge]: https://img.shields.io/github/actions/workflow/status/moryoav/besen/ci.yml?branch=main&style=flat-square&label=CI
[ci-url]: https://github.com/moryoav/besen/actions/workflows/ci.yml
[license-badge]: https://img.shields.io/github/license/moryoav/besen?style=flat-square
[license-url]: https://github.com/moryoav/besen/blob/main/LICENSE
