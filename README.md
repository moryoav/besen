# besen

[![release][release-badge]][release-url] [![CI][ci-badge]][ci-url] [![license][license-badge]][license-url]

`besen` is an async Python client for Besen EV chargers over Bluetooth Low Energy.
It provides the BLE connection management, login flow, protocol parsing, typed state
models, and charger control commands needed by applications such as Home Assistant
integrations.

## Home Assistant users

I maintain a HACS distribution of the Home Assistant Core Besen integration in
this repository, alongside the Python communication library. Install **Besen**
through HACS using
[`moryoav/besen`](https://my.home-assistant.io/redirect/hacs_repository/?owner=moryoav&repository=besen&category=integration),
then follow the [installation and upgrade guide](https://github.com/moryoav/besen/blob/main/docs/home-assistant-custom-integration.md).

HACS version **0.5.1** uses the accepted Core integration baseline, including
[the charger display temperature unit select](https://github.com/home-assistant/core/pull/180888).
It requires **Home Assistant 2026.9.2 or later** and installs `besen==0.4.4`
automatically. This library update waits for the charger's response to a start-charging
request and reports rejection or a missing response as a Home Assistant error.

I keep `main` aligned with accepted Core changes. Stable HACS releases can include
changes already merged into Core before they appear in a Home Assistant release.

I am validating this library update through HACS before marking
[the Core dependency PR](https://github.com/home-assistant/core/pull/182194)
ready for review. HACS 0.5.0 retains its original `besen==0.4.2` dependency.
The [alignment inventory](https://github.com/moryoav/besen/blob/main/docs/core-alignment.md)
records the exact baseline and necessary packaging and upgrade differences.

**Upgrading from 0.4.x:** language, device-name editing, LCD brightness, extra
sensors, and custom configuration/diagnostics flows are removed to match Core.
Status and temperature-option values now use Core's lowercase IDs. Review the
[upgrade notes](https://github.com/moryoav/besen/blob/main/docs/home-assistant-custom-integration.md#upgrading-from-04x)
for automation changes. HACS and Python library versions are now independent.

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
