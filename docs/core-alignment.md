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
| Dependency | `besen==0.4.2` | Keep the exact Core dependency and unchanged library implementation |
| Packaging | HACS and library shared release numbering | HACS 0.5.0; Python library remains 0.4.2; do not republish unchanged library artifacts |

## Necessary differences from Core

- Custom manifest version, repository documentation and issue links, bundled branding, and English translations.
- A small upgrade adapter fills the name missing from old manual entries, retires the old sync-clock option and repair issues, and migrates the charging-current unique ID. Existing entity IDs, names, history, and user-selected enabled states are retained. Removed entities can remain as unavailable registry entries until users remove them.
- Home Assistant 2026.9.2 or later is required by this release and is the integration test baseline. The Python library itself retains Python 3.12 compatibility.
- Home Assistant Core code retains its Apache 2.0 license; the existing communication library remains MIT licensed.

## Upgrade notes

Status sensor states and temperature options now use Core's stable lowercase IDs. Automations comparing raw values such as `Start`, `Connected Locked`, or `Fahrenheit` must use the corresponding Core IDs (`start`, `connected_locked`, `fahrenheit`). Existing entity IDs are retained where possible; new installations use Core names and defaults.

Language, device-name editing, brightness, extra sensors, and the old configuration/diagnostics flows are intentionally removed. The old clock option is ignored and removed; Core's default clock synchronization applies.

The new release does not change Bluetooth transport or protocol behavior. Testing with a physical charger through HACS remains the next validation step.
