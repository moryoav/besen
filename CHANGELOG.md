# Changelog

All notable changes to this project will be documented in this file.

This project follows semantic versioning where practical. Tags use a `v` prefix, for example `v0.1.0`.

## [0.4.6] - 2026-09-17 (Python library)

### Changed

- Log one `INFO` message when a previously usable charger becomes unavailable, including the device name and reason, and one `INFO` message when it is available again. This replaces the warning repeated every ten minutes and addresses Home Assistant's `log-when-unavailable` quality rule.
- Report recovery only after Bluetooth availability and authentication are both restored. Initial setup, intentional shutdown, and restart do not log outage or recovery messages.
- Report a PIN rejected while reconnecting with one `WARNING` per outage instead of an error on every watchdog cycle. The charger stays unavailable until the PIN is corrected.
- Move routine watchdog, login-retry, and connection-release details to `DEBUG`, and remove the duplicate reconnect success message. Unexpected packet-handling failures remain warnings.
- Charging commands, response correlation, retry behavior, timing, and public APIs are unchanged.

### Validation

- Cover each availability and authentication loss combination, long watchdog outages, duplicate disconnect callbacks, silent reconnect retries, rejected PINs across two outages, shutdown during an outage, and initial setup failures.
- Passed 196 tests and 66 snapshots with 96.39% combined coverage, plus Ruff, mypy, Core alignment, and package validation. No physical charger was operated for this logging-only change.

## [0.5.2] - 2026-09-14 (HACS integration)

### Fixed

- Bump the dependency to `besen==0.4.5` to correct charge-start response matching for both single-phase and three-phase chargers, including three-phase units that report connector 1.
- Preserve the accepted Core integration baseline and existing entities, settings, Bluetooth write modes, and automation behavior.

### Validation

- Passed 181 tests and 66 snapshots with 96.09% combined coverage, plus Ruff, mypy, Core alignment, and package validation.
- Verified the published library wheel and a physical three-phase stop/start at 6 A. Automated coverage includes single-phase charging across all supported Bluetooth write modes.

## [0.4.5] - 2026-09-14 (Python library)

### Fixed

- Match charge-start replies to the connector ID reported by telemetry instead of the single-phase or three-phase request selector. This fixes valid three-phase replies being ignored, followed by a false timeout and unnecessary Bluetooth disconnection.
- Correlate replies with the authenticated charger and serialized pending request when connector telemetry is not available yet, without guessing a connector ID from the phase count.
- Preserve the existing single-phase and three-phase start packets and supported Bluetooth write modes. Add debug logging of the response and expected connector ID.

### Validation

- Cover accepted and rejected responses for both phase counts, before and after connector telemetry, and preserve rejection of replies from another charger or a known different connector.
- Exercise single-phase charging with acknowledged-only, unacknowledged-only, and dual-mode GATT characteristics.
- Validate a physical three-phase BS20 stop/start at 6 A: connector 1 acknowledged the unchanged three-phase request in 0.092 seconds, without a forced disconnect.
- Passed 181 tests and 66 snapshots with 96.09% combined coverage, plus Ruff, mypy, Core alignment, and package validation.

## [0.5.1] - 2026-09-14 (HACS integration)

### Changed

- Bump the HACS integration dependency to `besen==0.4.4` so rejected or unconfirmed start-charging requests raise Home Assistant errors. Charging actions are not retried automatically.
- Record the dependency override while preserving the accepted Core source baseline and its alignment checks.

### Validation

- Passed 169 tests and 66 snapshots with 96.09% combined coverage, plus Ruff, mypy, Core alignment, and package validation.
- Physical charger validation through HACS remains pending before the Core dependency update is marked ready for review.

## [0.4.4] - 2026-09-14 (Python library)

### Fixed

- Wait for the charger response before completing a Python library start-charging request, and raise `CommandFailed` for reported rejection codes, disconnection, or a missing response.
- Serialize start-charging requests and retire the Bluetooth session after a timeout or cancellation so a late response cannot complete the next request. Do not retry the charging action automatically.

### Validation

- Add coverage for accepted and rejected requests, unknown error codes, unrelated responses, concurrent requests, transport failures, disconnection, cancellation, and late replies from a retired connection.
- Passed 169 tests and 66 snapshots with 96.09% combined coverage, plus Ruff, mypy, Core alignment, and package validation. Physical charger validation of response timing remains pending.

### Packaging

- Publish Python library releases with `library-vX.Y.Z` tags independently of the HACS integration version.

## [0.5.0] - 2026-09-14

### Changed

- Aligned the HACS integration with Home Assistant Core commit `1d38f3627ba11a1951784d93eb9f1ae019bd547e`, including PR #180888 and the earlier charging-current, status-sensor, and hardware-variant changes.
- Adopted Core setup, translated states, unknown-value handling, availability, entity defaults, and charger-screen temperature-unit control.
- Preserved existing entries and charging-current entity IDs through an upgrade adapter.
- Required Home Assistant 2026.9.2 or later for the custom integration.
- Kept the communication library unchanged at `besen==0.4.2`; separated HACS release numbering from Python library publishing.

### Breaking

- Removed language selection, charger-name editing, LCD brightness, RSSI/system-time/software-version sensor entities, the sync-clock option, and custom reauthentication, reconfiguration, diagnostics, and repair flows to match Core.
- Replaced raw status strings and temperature options with Core's stable lowercase IDs. Update automation comparisons and select action values as described in the upgrade guide.

### Validation

- Replaced lightweight integration stubs with Core-derived Home Assistant tests and added coverage for upgrades, entity identity preservation, and repeated setup.
- Added a recorded Core baseline and an automated check for unintended divergence.

## [0.4.3] - Withdrawn 2026-09-11

- Withdrawn the September 9 release following a report that initial connection no longer succeeds. A regression is suspected but has not been confirmed.
- Reverted the automatic service-cache clearing and discovery retry changes. Restored 0.4.2 as the latest supported release.
- Kept the remaining connection instability under investigation pending testing with improved Bluetooth reception.

## [0.4.2] - 2026-09-08

### Fixed

- Use acknowledged Bluetooth writes when the charger only advertises that write mode, including the single-phase BS20 variant reported in issue #1. Preserve unacknowledged writes on boards that support them.
- Select a complete, usable notification/write characteristic pair from discovered GATT characteristics instead of relying on service prefixes or assuming the old-board UUIDs exist.
- Report discovered service UUIDs and characteristic properties in debug logs when no supported pair is found.

### Validation

- Added regression coverage for single-phase login and commands, all supported write modes, reconnects, and missing or unusable characteristics.
- Full connection and charging validation on the reporter's single-phase hardware remains pending.

### Documentation

- Clarified the shared library and full-feature HACS release workflow on `main`, independent of selective Home Assistant Core submissions.
- Corrected the custom integration's sensor names and enabled defaults, and documented upgrades from the legacy `besen_bs20` domain.

## [0.4.1] - 2026-08-30

### Fixed

- Keep LCD brightness, language, and temperature unit state in sync after successful configuration commands.

## [0.4.0] - 2026-08-29

### Added

- Added session energy parsing for charging status commands 5 and 6.

### Changed

- Replaced the misleading `current_energy` and `current_amount` fields with `power`, `total_energy`, and `session_energy` fields that match the charger protocol.
- Return `None` for invalid temperature values and reject incomplete status payloads.
- Parse three-phase data from the protocol's exact 33-byte payload length.
- Updated the bundled Home Assistant custom integration to use the corrected telemetry fields and entity names.

## [0.3.4] - 2026-08-21

### Fixed

- Fixed reconnect handling when a charger keeps its previous application session after the Bluetooth connection is interrupted.
- Prevented duplicate login packets, stale callbacks, and incomplete cleanup from causing reconnect loops.

## [0.3.3] - 2026-07-30

### Fixed

- Updated project, documentation, badge, and contribution links after renaming the GitHub repository to `moryoav/besen`.

## [0.3.2] - 2026-07-06

### Fixed

- Replaced relative README links with absolute GitHub links so the PyPI project description does not point to missing `pypi.org/project/besen/...` pages.

## [0.3.1] - 2026-07-06

### Changed

- Replaced the PyPI-facing README with Python library usage and API documentation.
- Moved the Home Assistant custom integration README content to `docs/home-assistant-custom-integration.md`.

## [0.3.0] - 2026-07-06

### Changed

- Renamed the published Python distribution and import package from `besen-bs20` / `besen_bs20` to `besen`.
- Renamed the public Python client/data/error API to `BesenClient`, `BesenData`, and `BesenError`.
- Renamed the bundled Home Assistant custom integration domain from `besen_bs20` to `besen` and updated it to depend on `besen==0.3.0`.

## [0.2.2] - 2026-07-02

### Changed

- Corrected the displayed Celsius temperature-unit spelling while keeping the legacy `Celcius` command input as an alias.

## [0.2.1] - 2026-07-02

### Changed

- Limited repeated BLE unavailable watchdog warnings so Home Assistant logs are not flooded while the charger is unreachable.

## [0.2.0] - 2026-07-02

### Added

- Added a `besen-bs20` Python package containing the async BLE client, protocol parser, data models, and exceptions.
- Added package build validation to CI and PyPI trusted publishing to the tag release workflow.

### Changed

- Updated the Home Assistant integration to depend on `besen-bs20==0.2.0` instead of carrying protocol/client code inside `custom_components`.

## [0.1.9] - 2026-06-21

### Changed

- Prepared the README for HACS default submission by separating badges from the title and removing maintainer-only notes.

## [0.1.8] - 2026-06-20

### Changed

- Clarified that the integration is an unofficial community project with no BESEN affiliation or endorsement.
- Added stronger at-your-own-risk and liability disclaimer language for EV charger control.

## [0.1.7] - 2026-06-20

### Added

- Added strict mypy validation to CI and marked the integration as typed with `py.typed`.
- Added broad unit coverage for config flow, setup/unload, coordinator, entities, diagnostics, repairs, protocol parsing, and the fake BLE client paths.

### Changed

- Tightened type annotations across the integration and enabled an enforced 95% coverage gate.
- Updated quality-scale tracking for strict typing and test coverage.

## [0.1.6] - 2026-06-20

### Added

- Added README guidance for migrating from evseMQTT before installing the native integration.
- Added a link to the official Besen BS20 EV Charging Station product page.

### Changed

- Replaced generated brand images with the BESEN company logo.
- Aligned the Home Assistant manifest version metadata with the release version.

## [0.1.5] - 2026-06-20

### Fixed

- Matched entity display names to evseMQTT MQTT discovery labels, including phase voltage and amperage sensors.

## [0.1.4] - 2026-06-20

### Added

- Added community health documents, issue templates, and pull request template.
- Added `NOTICE.md` and restored canonical MIT license text for GitHub license detection.
- Increased BLE setup connection timeout/retries and added redacted setup diagnostics.
- Report missing active Bluetooth paths as `no_connectable_path` and document evseMQTT bridge contention.

## [0.1.3] - 2026-06-20

### Fixed

- Removed the unsupported `domains` key from `hacs.json` so HACS validation can pass.

## [0.1.2] - 2026-06-20

### Added

- Added README status badges and My Home Assistant install/configuration buttons.
- Added HACS and hassfest validation workflows.

## [0.1.1] - 2026-06-20

### Fixed

- Fixed the tag-triggered GitHub release workflow changelog extraction.

## [0.1.0] - 2026-06-20

### Added

- Initial native Home Assistant custom integration for Besen BS20 chargers.
- BLE protocol client based on the MIT-licensed `slespersen/evseMQTT` project.
- Home Assistant config flow with Bluetooth discovery, manual setup, reauthentication, and reconfiguration.
- Sensor, switch, number, select, and text platforms.
- Diagnostics and repair issue helpers.
- HACS metadata and local Home Assistant brand assets.
- CI for linting and tests.

### Known Limitations

- Hardware validation with a real Besen BS20 over ESPHome Bluetooth proxy is still required.
- Test coverage is currently protocol-focused; broader fake-BLE and Home Assistant config-flow coverage is planned.
- Firmware updates, charging history, Wi-Fi setup, device reset, and password reset are not implemented.
