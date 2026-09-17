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
| Extra flows | Reauthentication, reconfiguration, downloadable diagnostics, custom repairs | Remove features absent from Core; delete obsolete custom repair issues on upgrade |
| Tests | Integration internals mocked with lightweight stubs | Port Core integration tests to the custom-integration test harness; retain library tests and add upgrade coverage |
| Dependency | `besen==0.4.2` | HACS 0.5.3 uses `besen==0.4.6` for start-charging response handling and outage logging; the pinned Core baseline uses `0.4.2` |
| Packaging | HACS and library shared release numbering | HACS 0.5.3 and Python library 0.4.6 have independent releases |

## Necessary differences from Core

- HACS 0.5.3 and `main` use `besen==0.4.6` for start-charging response handling and outage logging while the pinned Core baseline uses `0.4.2`. This exact dependency override is recorded in `core-baseline.json`; all other baseline checks remain enforced. Published HACS 0.5.0 keeps its original 0.4.2 dependency.
- Custom manifest version, repository documentation and issue links, bundled branding, and English translations.
- A small upgrade adapter fills the name missing from old manual entries, retires the old sync-clock option and repair issues, and migrates the charging-current unique ID. Existing entity IDs, names, history, and user-selected enabled states are retained. Removed entities can remain as unavailable registry entries until users remove them.
- Home Assistant 2026.9.2 or later is required by this release and is the integration test baseline. The Python library itself retains Python 3.12 compatibility.
- Home Assistant Core code retains its Apache 2.0 license; the existing communication library remains MIT licensed.

## Upgrade notes

Status sensor states and temperature options now use Core's stable lowercase IDs. Automations comparing raw values such as `Start`, `Connected Locked`, or `Fahrenheit` must use the corresponding Core IDs (`start`, `connected_locked`, `fahrenheit`). Existing entity IDs are retained where possible; new installations use Core names and defaults.

Language, device-name editing, brightness, extra sensors, and the old configuration/diagnostics flows are intentionally removed. The old clock option is ignored and removed; Core's default clock synchronization applies.

HACS 0.5.3 waits for the charger response before completing a start-charging request and reports rejection, disconnection, or a missing response as an error. It retires the connection after a timeout or cancellation to prevent late responses from completing a later request. Charging actions are not retried automatically. The library fix was verified with a physical three-phase stop/start at 6 A and automated single-phase tests covering all supported Bluetooth write modes. Reply matching uses the reported connector ID rather than the phase selector. [Core PR #182194](https://github.com/home-assistant/core/pull/182194) tracks the dependency update.

Library 0.4.6 logs one `INFO` message when a previously usable charger becomes unavailable and one when Bluetooth and authentication are both restored, as required by Home Assistant's `log-when-unavailable` rule. A PIN rejected while reconnecting is reported with one warning per outage. The logging lives in the library, so no Core-aligned integration file changes.
