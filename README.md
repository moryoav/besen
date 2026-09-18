# Besen for Home Assistant & Python

[![GitHub Release][release-badge]][release-url]
[![PyPI][pypi-badge]][pypi-url]
[![HACS][hacs-badge]][hacs-url]
[![CI][ci-badge]][ci-url]
[![License][license-badge]](#attribution-and-license)

---

## ❤️ Help support this project

<p>
  <a href="https://ko-fi.com/Y5B124NZ2L"><img src="https://storage.ko-fi.com/cdn/kofi3.png?v=6" alt="Support me on Ko-fi" height="36"></a>
  &nbsp;
  <a href="https://github.com/sponsors/moryoav"><img src="https://img.shields.io/badge/Sponsor_on_GitHub-EA4AAA?style=for-the-badge&amp;logo=githubsponsors&amp;logoColor=white" alt="Sponsor on GitHub" height="36"></a>
</p>

Support ongoing development and maintenance by donating on Ko-fi or sponsoring the project on GitHub. Bug reports, compatibility feedback, and contributions are welcome too.

---

Control and monitor Besen EV chargers locally over Bluetooth Low Energy, without a cloud service.

This repository contains both the **Besen Home Assistant integration**, installable through HACS, and the **`besen` Python package** that handles communication with the charger. The Python package also powers the built-in Besen integration in Home Assistant Core.

## Which version should I use?

| Installation | Best for | How updates arrive |
| --- | --- | --- |
| **Built-in Home Assistant integration** | Users who prefer stability and the normal Home Assistant release cycle. | Included in Home Assistant; updated with Home Assistant Core. No HACS required. |
| **HACS custom integration** | Users who want new features and fixes sooner. | Releases from this repository, installed and updated through HACS. |

New features and fixes are developed here first, then submitted to Home Assistant Core. HACS releases can make them available before they complete Core review and reach a Home Assistant release. The two versions do not necessarily have the same features at the same time.

**For most users, start with the built-in integration.** Choose HACS for earlier access to changes and be prepared to report issues. Python developers can go straight to [Python package](#python-package).

## Supported chargers and prerequisites

The project has been verified with the **Besen BS20** and supports single-phase and three-phase charger data. Other Besen chargers advertising as `ACP#...` and using the same Bluetooth protocol may also work.

Before setup, have:

- The charger's **6-digit Bluetooth PIN**.
- A supported Bluetooth adapter or an **ESPHome Bluetooth proxy with active connections enabled**, within range of the charger.
- A free Bluetooth connection to the charger. Disconnect any phone app, MQTT bridge, or other client already connected to it. Each charger uses one active connection slot.

## Installation

### Option 1: Built-in Home Assistant integration

**Recommended for stability.** Besen is included in Home Assistant starting with **2026.9**. Use an up-to-date Home Assistant release; you do not need HACS or a manual package installation.

[![Add Besen to Home Assistant][ha-install-badge]][ha-install-url]

1. Click the button above, or open **Settings** > **Devices & services** > **Add integration** and search for **Besen**.
2. Follow the setup flow and enter the charger's Bluetooth PIN. You can also configure a charger from its discovery card.
3. Install future updates through the normal Home Assistant update process.

See the [official Besen documentation](https://www.home-assistant.io/integrations/besen/) for the functionality available in the built-in version.

### Option 2: HACS custom integration

**For earlier access to new features and fixes.** The current HACS release requires **Home Assistant 2026.9.2 or newer**. Check [release notes][release-url] for the requirements of the version you install.

Install and configure [HACS](https://www.hacs.xyz/docs/use/) first, then add this repository:

[![Open Besen in HACS][hacs-install-badge]][hacs-url]

1. Click the button above and add/open **Besen** in HACS. Alternatively, open **HACS** > **⋮** > **Custom repositories**, add `https://github.com/moryoav/besen`, and select type **Integration**.
2. Find **Besen** in HACS and download the latest release.
3. **Restart Home Assistant.**
4. For a new setup, click the button below or open **Settings** > **Devices & services** > **Add integration** > **Besen**. Select the discovered charger and enter its PIN.

[![Add Besen to Home Assistant][ha-install-badge]][ha-install-url]

**Already using the built-in Besen integration?** Keep your existing entry. After installing through HACS and restarting, the custom integration takes precedence. Do not add a second entry for the same charger.

<details>
<summary>Manual installation instead of HACS</summary>

Download a release from [GitHub Releases][release-url], and copy its `custom_components/besen` directory into your Home Assistant configuration directory as `/config/custom_components/besen`. The file `/config/custom_components/besen/manifest.json` must exist. Restart Home Assistant, then complete setup as above. Update this copy manually when installing a newer release.

</details>

## Features

The following describes the **integration in this repository**. The built-in version depends on your Home Assistant release and may not yet expose all of these entities.

| Control | Purpose |
| --- | --- |
| **Charge** switch | Start or stop charging. |
| **Charging current** number | Set the current limit from 6 A to the charger's reported maximum, with a 32 A fallback when no maximum is reported. |
| **Temperature unit** select | Choose Celsius or Fahrenheit on the charger's screen. This does not change Home Assistant's temperature units. |

| Sensors | Availability on a new installation |
| --- | --- |
| Charging power, total energy, session energy | Enabled by default. |
| Internal temperature, charging status, charging message | Enabled by default. |
| External temperature, error state, plug state, output state, current state | Diagnostic entities; disabled by default. |
| L1 voltage and current; L2/L3 voltage and current on three-phase chargers | Diagnostic entities; disabled by default. |

Enable optional entities from the charger's device page. Use **Total energy** for cumulative consumption in the Energy dashboard; **Session energy** can reset between charging sessions.

Use standard Home Assistant actions such as `switch.turn_on`, `switch.turn_off`, `number.set_value`, and `select.select_option` in automations. Temperature-select action values are `celsius` and `fahrenheit`.

Updates arrive through local Bluetooth notifications. The integration keeps a connection open and reconnects when needed. Entities become `unavailable` while disconnected or unauthenticated; missing or unsupported readings appear as `unknown`.

Wi-Fi provisioning, PIN/device resets, charging-history downloads, firmware updates, and safety-certified load balancing are not provided by this integration.

## Updates and switching versions

**Built-in:** update Home Assistant. **HACS:** install the update in HACS, then restart Home Assistant. Read the [release notes][release-url] and [changelog](https://github.com/moryoav/besen/blob/main/CHANGELOG.md) before upgrading.

**Returning from HACS to the built-in version:** make a backup and check that your installed Home Assistant release supports the features you need. Remove the downloaded Besen custom integration through HACS, or remove `/config/custom_components/besen` for a manual installation, then restart Home Assistant. Keep the existing Besen entry in **Devices & services**; deleting it is not part of switching versions. Features not yet included in that Core release will no longer be available, so check affected dashboards and automations.

## Troubleshooting

### Charger not discovered or no connectable Bluetooth path

Check **Settings** > **Connectivity** > **Bluetooth** > **Advertisement monitor** for an `ACP#...` device. Confirm that your proxy is connected to Home Assistant and supports active connections. Move it closer to the charger and disconnect other apps or bridges holding the charger's connection.

### Entities become unavailable

Check Bluetooth's **Connection monitor**, signal quality, and the proxy's available active-connection slots. Review the Home Assistant log for connection or authentication errors. For a persistent problem, enable debug logging for Besen, reproduce the issue, and review the logs before sharing them.

### PIN rejected

Use the current 6-digit charger PIN. If it changed after setup and your installed version does not offer reauthentication, remove and add the integration with the new PIN. Record any entity references first so you can check your automations afterward.

### HACS installation does not appear

Confirm that Home Assistant meets the release's minimum version, that `/config/custom_components/besen/manifest.json` exists, and that you restarted Home Assistant. Check the log for dependency or import errors.

## Python package

The reusable async Python client lives in `src/besen` and is published on [PyPI][pypi-url]. It provides BLE connection management, PIN authentication, typed state updates, and charger commands for applications outside Home Assistant as well.

For a standalone Python application, use **Python 3.12 or newer**:

```bash
pip install besen
```

Read the [Python library guide and API reference](https://github.com/moryoav/besen/blob/main/docs/python-library.md) for a working example, lifecycle and control methods, state fields, exceptions, and Bluetooth connection notes. Library capabilities are not a promise that an equivalent Home Assistant entity exists.

## Feedback and contributions

For HACS or Python package bugs, feature requests, and charger compatibility reports, [open an issue](https://github.com/moryoav/besen/issues/new/choose). Include your charger model, Home Assistant version where applicable, whether you use Core or HACS, and relevant release versions. Do not include PINs or other private information in reports or logs.

For a problem with the built-in integration, use the issue-reporting link in the [official Besen documentation](https://www.home-assistant.io/integrations/besen/).

Developers can refer to [CONTRIBUTING.md](https://github.com/moryoav/besen/blob/main/CONTRIBUTING.md) and the [Core alignment inventory](https://github.com/moryoav/besen/blob/main/docs/core-alignment.md).

## Safety

This software controls real electrical equipment and is not a safety controller. Keep the charger's hardware protections, wiring, and current limits appropriate for the installation. Test charging controls manually before relying on automations.

## Attribution and license

The Python communication library is licensed under [MIT](https://github.com/moryoav/besen/blob/main/LICENSE), with protocol work based on [slespersen/evseMQTT](https://github.com/slespersen/evseMQTT).

The Core-derived Home Assistant integration and tests are licensed under [Apache 2.0](https://github.com/moryoav/besen/blob/main/custom_components/besen/LICENSE). See [NOTICE.md](https://github.com/moryoav/besen/blob/main/NOTICE.md) for attribution details.

[release-badge]: https://img.shields.io/github/v/release/moryoav/besen?style=flat-square
[release-url]: https://github.com/moryoav/besen/releases
[pypi-badge]: https://img.shields.io/pypi/v/besen?style=flat-square&label=PyPI
[pypi-url]: https://pypi.org/project/besen/
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=flat-square
[hacs-url]: https://my.home-assistant.io/redirect/hacs_repository/?owner=moryoav&repository=besen&category=integration
[hacs-install-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[ha-install-badge]: https://my.home-assistant.io/badges/config_flow_start.svg
[ha-install-url]: https://my.home-assistant.io/redirect/config_flow/?domain=besen
[ci-badge]: https://img.shields.io/github/actions/workflow/status/moryoav/besen/ci.yml?branch=main&style=flat-square&label=CI
[ci-url]: https://github.com/moryoav/besen/actions/workflows/ci.yml
[license-badge]: https://img.shields.io/badge/License-MIT%20%2F%20Apache--2.0-blue.svg?style=flat-square
