# Contributing to Besen for Home Assistant

Thanks for your interest in improving Besen for Home Assistant.

This repository contains one Home Assistant custom integration:

- `custom_components/besen`: the Besen integration, BLE protocol
  client, config flow, entities, diagnostics, repairs, translations, and brand
  assets.

Contributions are welcome, including bug reports, documentation improvements,
compatibility reports, BLE reliability fixes, security hardening, and focused
feature ideas.

## Before You Start

Please open an issue before starting large or risky changes. This helps avoid
duplicated work and gives maintainers a chance to discuss the approach first.

Small fixes, documentation updates, and clearly scoped bug fixes can usually go
straight to a pull request.

## Reporting Bugs

When reporting a bug, please include:

- The Besen integration version you are using.
- Your Home Assistant version.
- Whether you installed through HACS, manually, or from the development branch.
- Your charger model or advertised BLE name, if known.
- Whether Home Assistant connects through a local Bluetooth adapter or an
  ESPHome Bluetooth proxy.
- Clear steps to reproduce the issue.
- Relevant Home Assistant logs with sensitive information removed.
- What you expected to happen.
- What actually happened.

Please remove charger PINs, private BLE addresses, private logs, Wi-Fi details,
personal paths, and private Home Assistant configuration before sharing logs,
diagnostics, or screenshots.

## Suggesting Features

Feature requests are welcome. Please describe:

- The problem you want to solve.
- The Home Assistant workflow you expect to use.
- Whether the change affects discovery, setup, BLE connection handling,
  charger controls, entities, diagnostics, documentation, or compatibility with
  charger variants.
- Any safety, privacy, or reliability concerns the feature may introduce.

Because this project can control EV charging hardware, new controls should have
clear failure behavior and should not bypass electrical safety protections.

## Development Setup

Clone the repository:

```bash
git clone https://github.com/moryoav/ha_besen.git
cd ha_besen
```

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

The repository layout is:

```text
custom_components/besen/  Home Assistant custom integration
tests/                         Lightweight local tests
.github/workflows/             CI, HACS, Hassfest, and release workflows
```

For local Home Assistant testing, copy the integration into:

```text
/config/custom_components/besen
```

Restart Home Assistant and add the integration from **Settings** -> **Devices &
services** -> **Add integration** -> **Besen**. For BLE proxy testing, make
sure the ESPHome Bluetooth proxy supports active connections and is close enough
to the charger.

## Pull Request Guidelines

Please keep pull requests focused. A good pull request should:

- Explain what changed and why.
- Mention any related issue.
- Keep unrelated formatting or refactoring out of the change.
- Update documentation when behavior, installation, options, entities, or
  troubleshooting guidance changes.
- Include screenshots when changing Home Assistant UI text or flow behavior.
- Avoid committing secrets, charger PINs, private BLE addresses, private logs,
  Wi-Fi details, or personal Home Assistant configuration.

If you change the integration version, update these files consistently:

- `pyproject.toml`
- `custom_components/besen/manifest.json`
- `custom_components/besen/const.py`
- `CHANGELOG.md`

## Testing

Before opening a pull request, test the parts you changed as much as practical.

For local validation, run:

```bash
python -m ruff check .
python -m pytest -q
python -m compileall custom_components tests
```

For integration changes, verify that Home Assistant can:

- Load the `besen` integration.
- Complete the config flow or discovery flow.
- Connect to the charger through the intended Bluetooth path.
- Create and update the expected entities.
- Reload or restart without relevant errors.

For documentation-only changes, please check that links, paths, and examples are
accurate. This repository may not have full automated coverage for every Home
Assistant path yet, so clear manual test notes in the pull request are helpful.

## Security Notes

Please be especially careful with changes involving:

- Charger PIN handling and reauthentication.
- BLE command construction, parsing, notification handling, and reconnects.
- Diagnostics and data redaction.
- Logs that may include BLE addresses, charger identifiers, or private Home
  Assistant configuration.
- Charging controls such as start, stop, and charge current.

If you believe you found a security vulnerability, please do not open a public
issue with exploit details. Follow `SECURITY.md` instead.

## Safety Notes

This integration is not a safety controller. It must not be relied on as the
only protection for electrical limits, overheating, grid constraints, vehicle
safety, or local code requirements.

Do not use issues or pull requests to request advice about unsafe wiring,
breaker sizing, bypassing charger protections, or electrical work that should be
handled by a qualified professional.

## Documentation

Please update documentation when changing user-facing behavior.

Depending on the change, this may include:

- `README.md`
- `CHANGELOG.md`
- `custom_components/besen/strings.json`
- `custom_components/besen/quality_scale.yaml`

Use plain, direct language and include Home Assistant examples where they make
the workflow easier to understand.

## Releases

Stable users should use the default repository URL:

```text
https://github.com/moryoav/ha_besen
```

Published GitHub releases are preferred for HACS users. Tags use the `vX.Y.Z`
format.

## Code of Conduct

Please be respectful, constructive, and patient. This project is intended to
help Home Assistant users control their own chargers safely and reliably.
