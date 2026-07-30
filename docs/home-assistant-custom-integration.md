# Besen Home Assistant Custom Integration
[![HACS][hacs-badge]][hacs-url] [![release][release-badge]][release-url] ![downloads][downloads-badge] [![hassfest][hassfest-badge]][hassfest-url] [![validate][validate-badge]][validate-url] [![license][license-badge]][license-url]

Native Home Assistant integration for Besen EV chargers over Bluetooth Low Energy. This has been verified with the BS20 model.

This integration talks directly to the charger through Home Assistant's Bluetooth stack. It does not need MQTT, Docker, a sidecar process, or a Home Assistant add-on. It is designed to work through existing ESPHome Bluetooth proxies as long as those proxies support active GATT connections.

## Python Library

The reusable BLE client and protocol parser are published as the `besen` Python package. Home Assistant installs that package as this integration's communication dependency.

```bash
pip install besen
```

## Disclaimer

This is an unofficial community project. It is not affiliated with, associated with, authorized by, endorsed by, or in any way officially connected with BESEN, Besen Group, or any related company. Product names, trademarks, and registered trademarks belong to their respective owners and are used only to identify compatible devices.

Use this integration at your own risk. EV charging equipment controls real electrical hardware; incorrect configuration, device firmware behavior, Bluetooth issues, automation mistakes, or software defects may cause charging interruption, equipment damage, vehicle damage, electrical hazards, or other loss. The maintainer and contributors are not responsible or liable for damage, injury, data loss, costs, or other consequences arising from use of this integration.

## Requirements

- Home Assistant with the Bluetooth integration enabled.
- A Besen charger advertising as `ACP#...`; the BS20 model has been verified.
- The charger BLE address and 6-digit PIN.
- For ESPHome Bluetooth proxies:
  - `bluetooth_proxy:` with active connections enabled.
  - A connectable proxy close enough to the charger.
  - Enough free active connection slots.

ESPHome Bluetooth proxies default to active connections enabled in current ESPHome releases. Each continuously connected charger uses one active GATT connection slot on the selected proxy.

## Migrating From evseMQTT

If you previously used evseMQTT with the same charger, fully stop or terminate the old evseMQTT bridge before installing this integration. This includes any Docker container, Home Assistant add-on, Raspberry Pi service, systemd unit, or other process that may still connect to the charger.

The charger can only keep one active BLE client connection. In some cases, after evseMQTT has been stopped, you may also need to turn the EV charger off and back on so it forgets the old component pairing before Home Assistant can discover or connect to it through this integration.

## Installation

### HACS custom repository

[![Open the Besen HACS repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=moryoav&repository=besen&category=integration)

1. Open HACS.
2. Add this repository as a custom integration repository.
3. Install **Besen**.
4. Restart Home Assistant.
5. Go to **Settings > Devices & services**.
6. Add **Besen** or accept the discovered `ACP#...` device.

HACS uses GitHub releases when they are available. Install the latest release tag unless you explicitly want to test the default branch.

### Manual installation

1. Copy `custom_components/besen` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add **Besen** from **Settings > Devices & services**.

## Configuration

[![Add the Besen integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=besen)

- **BLE address**: The charger Bluetooth address. Discovery fills this automatically when Home Assistant sees an `ACP#...` advertisement.
- **PIN**: The charger's 6-digit Bluetooth PIN. Many units default to `123456`.
- **Sync charger clock**: Keeps the charger's internal clock aligned during heartbeat responses.

The PIN can be updated later through the integration reconfigure flow.

## Entities

The exact entity set depends on charger model, board revision, reported phase count, and supported firmware responses.

Enabled by default:

- Charge switch.
- Charge amps number.
- Current Energy sensor.
- Total/session energy sensors.
- L1 Voltage and L1 Amperage.
- Charger status, plug state, output state, current state, and error state.
- Charger temperature.
- Device name text entity.
- Temperature unit and language selectors.

Diagnostic or less commonly used entities may be disabled by default:

- RSSI.
- L2/L3 Voltage and Amperage on three-phase chargers.
- System time.
- LCD brightness.
- Integration/protocol version details.

## Controls And Actions

The integration does not register custom Home Assistant service actions. Use the standard entity actions instead:

- `switch.turn_on` / `switch.turn_off` on the charging switch.
- `number.set_value` on charge amps.
- `select.select_option` on language or temperature unit.
- `text.set_value` on the charger name.

Command failures are raised back to Home Assistant and the device is marked unavailable if the BLE write path fails.

## Updating Data

The charger sends status over BLE notifications after login. Home Assistant keeps one active BLE connection open, listens for notifications, and responds to charger heartbeats. If notifications stop for about 45 seconds, the integration reconnects without repeatedly filling the logs.

This is a local-push integration. There is no cloud dependency.

## Common Automations

Start charging when solar surplus is available:

```yaml
alias: Start EV charging on solar surplus
triggers:
  - trigger: numeric_state
    entity_id: sensor.solar_surplus_power
    above: 2500
    for: "00:05:00"
conditions:
  - condition: state
    entity_id: sensor.besen_plug_state
    state: Connected Locked
actions:
  - action: number.set_value
    target:
      entity_id: number.besen_charge_amps
    data:
      value: 8
  - action: switch.turn_on
    target:
      entity_id: switch.besen_charging
```

Stop charging before peak tariff:

```yaml
alias: Stop EV charging before peak tariff
triggers:
  - trigger: time
    at: "17:00:00"
actions:
  - action: switch.turn_off
    target:
      entity_id: switch.besen_charging
```

## Supported Devices

Known target:

- [Besen BS20 EV Charging Station](https://www.besen-group.com/products/ev-charging-station/bs20/).

Likely compatible:

- Besen wallboxes using the same `ACP#` BLE protocol and one of the known UUID pairs.

Unsupported or not implemented:

- Wi-Fi provisioning.
- Password reset.
- Device reset.
- Charging history download.
- Firmware updates through Home Assistant.
- Safety-certified load balancing.

## Troubleshooting

### The charger is not discovered

- Confirm it appears in **Settings > Bluetooth > Advertisement monitor** as `ACP#...`.
- Move an ESPHome Bluetooth proxy closer to the charger.
- Make sure the proxy is added to Home Assistant through the ESPHome integration.
- Run an active scan or temporarily place a local Bluetooth adapter near the charger.

### Setup says no connectable Bluetooth path is available

The charger may be visible only through a passive/non-connectable adapter. Use an ESPHome Bluetooth proxy with active connections enabled, or a local Bluetooth adapter supported by Home Assistant.

Stop any existing evseMQTT bridge, Docker container, add-on, Raspberry Pi service, or other app that is already connected to the charger before setting up this integration. The charger can expose live data through the old MQTT bridge while Home Assistant has no free connectable BLE path for the native integration.

### The charger becomes unavailable

- Check **Settings > Bluetooth > Connection monitor**.
- Verify the proxy has free active connection slots.
- Stop any old evseMQTT/MQTT bridge or companion process that may still hold the charger's BLE connection.
- Prefer Ethernet ESP32 Bluetooth proxies when possible.
- Avoid placing the proxy next to strong Wi-Fi or USB 3.0 interference sources.

### The PIN is rejected

Use the integration reauthentication prompt or reconfigure flow to enter the correct 6-digit PIN. The integration redacts PINs from diagnostics.

### Diagnostics

From the device page, download diagnostics before opening an issue. Diagnostics include the board revision, charger metadata, latest parsed state, availability, and last error. The PIN is redacted.

## Removal

1. Go to **Settings > Devices & services**.
2. Open **Besen**.
3. Select the integration menu and choose **Delete**.
4. Restart Home Assistant if you also manually copied the integration files and want to remove them from `custom_components`.

## Safety Notes

This integration exposes charger controls but is not a safety controller. Do not rely on it as the only protection for electrical limits, overheating, grid constraints, or vehicle safety. Keep charger hardware, breaker sizing, wiring, and local electrical code protections correct independently of Home Assistant. Use manual supervision and conservative automation defaults when controlling charging equipment.

## Attribution

The Bluetooth protocol implementation is based on the MIT-licensed work in [slespersen/evseMQTT](https://github.com/slespersen/evseMQTT), with the MQTT/runtime portions replaced by native Home Assistant integration code.

Additional attribution details are maintained in [NOTICE.md](https://github.com/moryoav/besen/blob/main/NOTICE.md).

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=flat-square
[hacs-url]: https://github.com/hacs/integration
[release-badge]: https://img.shields.io/github/v/release/moryoav/besen?style=flat-square
[release-url]: https://github.com/moryoav/besen/releases
[downloads-badge]: https://img.shields.io/github/downloads/moryoav/besen/total?style=flat-square
[hassfest-badge]: https://img.shields.io/github/actions/workflow/status/moryoav/besen/hassfest.yaml?branch=main&style=flat-square&label=hassfest
[hassfest-url]: https://github.com/moryoav/besen/actions/workflows/hassfest.yaml
[validate-badge]: https://img.shields.io/github/actions/workflow/status/moryoav/besen/validate.yaml?branch=main&style=flat-square&label=validate
[validate-url]: https://github.com/moryoav/besen/actions/workflows/validate.yaml
[license-badge]: https://img.shields.io/github/license/moryoav/besen?style=flat-square
[license-url]: https://github.com/moryoav/besen/blob/main/LICENSE
