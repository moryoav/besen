# Home Assistant Core alignment

## Baseline

HACS 0.5.0 aligns with Home Assistant Core commit `1d38f3627ba11a1951784d93eb9f1ae019bd547e`, merged in [PR #180888](https://github.com/home-assistant/core/pull/180888). This is the latest merged Besen implementation, including the hardware compatibility, charging-current, status-sensor, and temperature-display changes. It is not limited to the current Home Assistant stable release.

## Alignment inventory

| Area | Previous HACS 0.4.2 | Core baseline and alignment |
| --- | --- | --- |
| Setup | Free-text address, separate sync-clock setting, `isdigit()` PIN validation | Discovered-device selection, Core clock behavior, decimal PIN validation |
| Entry lifecycle | Custom runtime wrapper, cleanup and repair handling | Core coordinator lifecycle, error translations, and availability checks |
| Charging control | Charge switch and charge-amps number | Core charge switch and charging-current number; migrate the number unique ID while retaining its entity ID |
| Temperature display | Raw Celsius/Fahrenheit options | Core `celsius`/`fahrenheit` option IDs and translated labels; changes the charger screen only |
| Status sensors | Raw protocol strings, including undocumented placeholders | Core translated state IDs, `None` for unknown values, and Core diagnostic defaults |
| Telemetry | Power, energy, temperatures, phase readings | Keep the same Core measurements and phase-dependent entity creation |
| Extra controls | Language, device-name editing, LCD brightness | Remove from the custom integration |
| Extra sensors | RSSI, system time, software-version entity | Remove from the custom integration; firmware remains device metadata |
| Extra flows | Reauthentication, reconfiguration, downloadable diagnostics, custom repairs | Remove features absent from Core; delete obsolete custom repair issues on upgrade. HACS 0.5.4 restores PIN reauthentication ahead of Core. HACS 0.5.8 removes the reconfiguration restored in 0.5.7 because Core marks it exempt |
| Tests | Integration internals mocked with lightweight stubs | Port Core integration tests to the custom-integration test harness; retain library tests and add upgrade coverage |
| Dependency | `besen==0.4.2` | HACS 0.5.4 uses `besen==0.4.7` for start-charging response handling, outage logging, and PIN rejection state; `main` uses `besen==0.4.8` for session fields; the pinned Core baseline uses `0.4.2` |
| Packaging | HACS and library shared release numbering | HACS 0.5.4 and Python library 0.4.7 have independent releases |

## Necessary differences from Core

- HACS 0.5.4 through 0.5.8 use `besen==0.4.7` for start-charging response handling, outage logging, and PIN rejection state while the pinned Core baseline uses `0.4.2`. `main` uses `besen==0.4.8`, which adds the session fields. This exact dependency override is recorded in `core-baseline.json`. Published HACS 0.5.0 keeps its original 0.4.2 dependency.
- HACS 0.5.4 restores PIN reauthentication ahead of Core, so `config_flow.py`, `coordinator.py`, `quality_scale.yaml`, and `strings.json` differ from the baseline. `core-baseline.json` keeps the Core checksums and records each file's checksum and reason as a development override; any other change still fails the alignment check. The `config_flow.py` override also rejects PINs with non-ASCII digits, and the `quality_scale.yaml` override matches Core's current checklist. The overrides can be removed once a Core PR adopts these changes.
- `main` adds five read-only session sensors ahead of Core, so `sensor.py` is also a development override and the `strings.json` override also names these sensors. See [session-sensors.md](session-sensors.md).
- Custom manifest version, repository documentation and issue links, bundled branding, and English translations.
- A small upgrade adapter fills the name missing from old manual entries, retires the old sync-clock option and repair issues, and migrates the charging-current unique ID. Existing entity IDs, names, history, and user-selected enabled states are retained. Removed entities can remain as unavailable registry entries until users remove them.
- Home Assistant 2026.9.2 or later is required by this release and is the integration test baseline. The Python library itself retains Python 3.12 compatibility.
- Home Assistant Core code retains its Apache 2.0 license; the existing communication library remains MIT licensed.

## Upgrade notes

Status sensor states and temperature options now use Core's stable lowercase IDs. Automations comparing raw values such as `Start`, `Connected Locked`, or `Fahrenheit` must use the corresponding Core IDs (`start`, `connected_locked`, `fahrenheit`). Existing entity IDs are retained where possible; new installations use Core names and defaults.

Language, device-name editing, brightness, extra sensors, and the old configuration/diagnostics flows are intentionally removed. The old clock option is ignored and removed; Core's default clock synchronization applies.

HACS 0.5.4 waits for the charger response before completing a start-charging request and reports rejection, disconnection, or a missing response as an error. It retires the connection after a timeout or cancellation to prevent late responses from completing a later request. Charging actions are not retried automatically. The library fix was verified with a physical three-phase stop/start at 6 A and automated single-phase tests covering all supported Bluetooth write modes. Reply matching uses the reported connector ID rather than the phase selector. [Core PR #182194](https://github.com/home-assistant/core/pull/182194) tracks the dependency update.

Library 0.4.6 logs one `INFO` message when a previously usable charger becomes unavailable and one when Bluetooth and authentication are both restored, as required by Home Assistant's `log-when-unavailable` rule. A PIN rejected while reconnecting is reported with one warning per outage. The logging lives in the library, so no Core-aligned integration file changes.

HACS 0.5.4 restores PIN reauthentication with library 0.4.7. When the charger explicitly rejects the saved PIN during setup or reconnection, Home Assistant opens a reauthentication prompt. The replacement PIN is validated with the same charger before the existing entry is updated and reloaded, so entity IDs, history, names, and options are retained. Automatic reconnect attempts pause after a rejection, and Bluetooth outages or incomplete logins never ask for a PIN. Reconfiguration, diagnostics, and custom repair flows remain removed. The integration's quality scale checklist marks `reauthentication-flow` and `action-exceptions` done; the manifest tier remains Bronze until Core accepts Silver.

HACS 0.5.7 briefly restored PIN reconfiguration. Core then marked `reconfiguration-flow` exempt for Besen in [Core PR #183626](https://github.com/home-assistant/core/pull/183626): the Bluetooth address is the unique ID, and a changed PIN is handled by the reauthentication flow. HACS 0.5.8 removes the reconfigure step and records the same exemption, so its quality scale checklist matches Core. The rejection of PINs with non-ASCII digits from 0.5.7 stays. Custom repair flows remain removed.

Core then marked `repair-issues` exempt in [Core PR #183733](https://github.com/home-assistant/core/pull/183733) and promoted Besen to Platinum in [Core PR #183742](https://github.com/home-assistant/core/pull/183742). `main` mirrors both in `quality_scale.yaml` and the manifest, which ship with the next HACS release.
