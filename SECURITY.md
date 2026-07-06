# Security Policy

Besen for Home Assistant stores a charger PIN and can send BLE commands
that control EV charging behavior. Please treat security, privacy, and safety
issues with care.

## Supported Versions

Security fixes are intended for the latest published release and the current
`main` branch. Older releases are not actively supported unless a maintainer
says otherwise in a specific issue or release note.

## Reporting a Vulnerability

Please do not open a public issue with exploit details, working
proof-of-concept code, charger PINs, private BLE addresses, private logs, Wi-Fi
details, or personal Home Assistant configuration.

If GitHub private vulnerability reporting is available for this repository, use
the **Report a vulnerability** button on the Security tab.

If private vulnerability reporting is not available, open a minimal public issue
that says you have a security concern and asks the maintainer to arrange private
disclosure. Do not include sensitive details in that issue.

## What to Include

When reporting a vulnerability privately, include as much of the following as
you can safely share:

- A clear description of the issue.
- The affected version or commit.
- Steps to reproduce in a safe test environment.
- The expected impact.
- Any relevant logs with secrets and private data removed.
- Suggested mitigations, if you know them.

## Security-Sensitive Areas

Please use extra care when changing or reviewing:

- Charger PIN storage, redaction, and reauthentication.
- BLE command generation, parsing, notification handling, and reconnect logic.
- Diagnostics and repair issue data.
- Logging around setup, pairing, BLE addresses, charger identifiers, and
  command failures.
- Charging controls such as start, stop, charge current, and device settings.

## Responsible Testing

Test security reports and fixes only in an environment you own or have
permission to use.

Do not attempt to access, modify, interrupt, or disclose another person's Home
Assistant instance, charger, vehicle, BLE devices, credentials, logs, network,
or electrical installation.

## Public Disclosure

Please give the maintainer reasonable time to investigate and fix confirmed
vulnerabilities before publishing details publicly.

Coordinated disclosure helps protect users while a fix is prepared.
