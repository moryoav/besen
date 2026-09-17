# Besen for Home Assistant

I maintain this HACS distribution using the accepted Home Assistant Core Besen integration baseline. HACS **0.5.3** is based on [Core PR #180888](https://github.com/home-assistant/core/pull/180888) and requires **Home Assistant 2026.9.2 or later**. Home Assistant installs `besen==0.4.6` automatically. It logs one message when the charger becomes unavailable and one when it recovers, and keeps the corrected charge-start reply matching for both single-phase and three-phase chargers.

I verified the charge-start fix with a physical three-phase stop/start and automated single-phase compatibility tests. [The Core dependency PR](https://github.com/home-assistant/core/pull/182194) tracks this update.

The [alignment inventory](core-alignment.md) records the complete comparison and upgrade differences. Core changes can reach this repository before the next Home Assistant release.

## Supported devices

Besen BS20 single-phase and three-phase chargers using the `ACP#` Bluetooth protocol are supported. Other Besen chargers using that protocol may also work.

## Prerequisites

- Home Assistant 2026.9.2 or later.
- The charger's 6-digit Bluetooth PIN.
- A Bluetooth adapter or ESPHome Bluetooth proxy that supports active GATT connections.
- A free connection to the charger. Stop any app or bridge already connected to it.

## Installation

1. Open HACS and add `https://github.com/moryoav/besen` as a custom repository of type **Integration**.
2. Install **Besen** and restart Home Assistant.
3. Go to **Settings** > **Devices & services** and add **Besen**, or accept the discovered charger.
4. Select the discovered charger and enter its PIN.

A custom integration with domain `besen` takes precedence over the built-in integration. An existing entry uses the installed custom version after restarting; do not create a second entry for the same charger.

For manual installation, copy `custom_components/besen` into the Home Assistant configuration directory and restart.

## Upgrading from 0.5.x

Install **0.5.3** in HACS and restart Home Assistant. Existing entries and entities are retained. This release replaces the repeated unavailable warning with one log message per outage and one on recovery, and includes the 0.5.2 fix for the response-matching regression in 0.5.1. Existing single-phase and three-phase commands and Bluetooth write modes are preserved. Charging actions are not retried automatically.

## Upgrading from 0.4.x

Install **0.5.3** in HACS and restart Home Assistant. If the version is not listed, refresh the repository information and check the minimum Home Assistant version above.

Existing `besen` entries are retained. The upgrade supplies the name missing from older manual entries and migrates **Charge Amps** to Core's **Charging current** identifier while retaining its existing entity ID, custom name, device association, and history. Existing user choices about enabled entities are retained; Core defaults apply to newly created entities.

These features are removed to match Core:

- Language selection, charger-name editing, and LCD brightness control.
- RSSI, system-time, and software-version sensor entities. Firmware information remains in device information.
- The sync-clock option, reauthentication/reconfiguration forms, downloadable diagnostics, and custom repair issues. Core's default clock synchronization applies.

Removed entities may remain listed as unavailable. Remove their dashboard and automation references, then delete their unused entity registry entries if desired.

Status sensor states and temperature options now use Core's stable IDs. Update automations or scripts that use raw protocol strings:

| Previous value | Core value |
| --- | --- |
| `Start` | `start` |
| `Connected Locked` | `connected_locked` |
| `Charging` | `charging` |
| `Celsius` | `celsius` |
| `Fahrenheit` | `fahrenheit` |

Check the current state in **Developer tools** > **States** when updating other comparisons. Unknown protocol values now produce `unknown`, rather than an invented `unknown_0` or similar state.

The withdrawn 0.4.3 release is not reused. HACS and Python library versions are independent: HACS 0.5.3 uses Python library 0.4.6.

### Older installations

The legacy `besen_bs20` domain from 0.2.x has no automatic migration. Disable that entry before setting up **Besen**, then update entity references and remove the old entry after verifying the new one.

## Supported functionality

### Controls

- **Charge** switch: starts or stops charging.
- **Charging current** number: sets the current limit from 6 A to the maximum reported by the charger, with a 32 A fallback if no maximum is reported.
- **Temperature unit** select: chooses **Celsius** or **Fahrenheit** for the charger's screen. It does not change Home Assistant's unit system or temperature sensor display units.

Use `switch.turn_on`, `switch.turn_off`, `number.set_value`, and `select.select_option`. The temperature select's action values are `celsius` and `fahrenheit`.

### Sensors

Enabled by default on new installations:

- Charging power, total energy, and session energy.
- Internal temperature.
- Charging status and charging message.

Diagnostic sensors disabled by default on new installations:

- External temperature.
- Error state, plug state, output state, and current state.
- L1 voltage and current.
- L2/L3 voltage and current, created only for three-phase chargers.

Enable diagnostic entities from the charger device page when needed. Use **Total energy** for cumulative consumption in the Energy dashboard; session energy can reset between charging sessions.

## Data updates

The integration uses local Bluetooth notifications. It keeps one active connection, responds to heartbeats, and reconnects when notifications stop. There is no cloud dependency.

The temperature select updates when the command is sent successfully and when the charger reports the setting. Entities become `unavailable` while the connection is unavailable or authentication is incomplete. Missing or unsupported values appear as `unknown`.

## Known limitations

Language, charger-name editing, LCD brightness, extra diagnostic sensors, Wi-Fi provisioning, password/device reset, charging-history downloads, and firmware updates are not exposed. This integration does not provide safety-certified load balancing.

## Troubleshooting

### The charger is not discovered

**Symptom:** The charger is missing from setup.

**Resolution:**

1. Check **Settings** > **Connectivity** > **Bluetooth** > **Advertisement monitor** for `ACP#...`.
2. Move an active Bluetooth proxy closer to the charger.
3. Stop other apps or bridges that could hold its connection.

### The charger becomes unavailable

**Symptom:** Charger entities show `unavailable` or setup reports no connectable Bluetooth path.

**Resolution:**

1. Check the Bluetooth connection monitor and the proxy's free connection slots.
2. Improve reception and reduce nearby Wi-Fi or USB interference.
3. Prefer an Ethernet-connected proxy when practical.
4. Check the Home Assistant log. The integration logs one message with the reason when the charger becomes unavailable and one when it is available again. A warning that the charger rejected the configured PIN means the PIN changed; see below.
5. Enable debug logging for the integration, reproduce the issue, and attach the logs to a GitHub issue if it continues.

### The PIN is rejected

**Symptom:** Setup reports an invalid PIN.

**Resolution:** Use the current 6-digit charger PIN. If the PIN changed after setup, remove and add the integration again, as with the Core integration.

## Removal

Delete the Besen entry from **Settings** > **Devices & services**. To return to the built-in integration, remove the custom integration through HACS and restart Home Assistant.

## Attribution

The integration and its tests are adapted from Home Assistant Core under Apache 2.0. The communication library is based on the MIT-licensed work in [slespersen/evseMQTT](https://github.com/slespersen/evseMQTT). See [NOTICE.md](../NOTICE.md).
