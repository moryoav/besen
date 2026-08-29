# Changelog

All notable changes to this project will be documented in this file.

This project follows semantic versioning where practical. Tags use a `v` prefix, for example `v0.1.0`.

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
