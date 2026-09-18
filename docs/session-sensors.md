# Session and reservation sensors (unreleased)

The custom integration adds five read-only sensors alongside Session energy.
All five are enabled by default for single- and three-phase chargers.

| Entity name | Native value | Meaning |
| --- | --- | --- |
| Session start | Timestamp | Charger-reported session initialization/start time, not necessarily the instant power delivery began. |
| Session duration | Seconds | Elapsed duration reported by the charger, not a locally running timer. |
| Session current limit | Amperes | Limit recorded for this session, separate from the configurable Charging current number. |
| Reservation start | Timestamp | Reservation time retained in the session report. |
| Reservation duration | Minutes | Reported maximum duration for the session/reservation; unknown when unset or unlimited. |

The last reported values may remain after a session ends. Missing fields are
unknown before the first session report. Zero duration remains a valid zero;
unset timestamps and unset/unlimited limits are not displayed as dates or
large numbers. A subsequent empty report clears previous optional values.
All sensors become unavailable when the connection or authentication is lost.
No reservation controls, additional polling, or charging commands are added.

## Protocol and validation

The existing parser handles both current (`0x0005`) and completed (`0x0006`)
session reports, requiring at least 74 payload bytes. Session energy decoding
and the existing electrical/status sensors are unchanged.

| Field | Payload bytes (zero-based, end exclusive) |
| --- | --- |
| Maximum duration, minutes | `[20:22]` |
| Reservation timestamp | `[26:30]` |
| Session current limit | `[46:47]` |
| Session timestamp | `[47:51]` |
| Elapsed duration, seconds | `[51:55]` |
| Session energy (existing) | `[63:67]` |

The field layout was cross-checked against
[EVSEMaster's parser](https://github.com/RafaelSchridi/evsemaster/blob/main/evsemaster/protocol.py).
The implementation uses Besen's existing timestamp conversion and returns
timezone-aware datetime values to Home Assistant. It does not add EVSEMaster's
per-device clock-skew compensation or change clock synchronization.

Automated tests cover both command types, packet framing, units, extended and
truncated payloads, sentinel values, model merging, Home Assistant entity
metadata, push updates, clearing old values, and connection/authentication
availability. Hardware validation is still required: compare the timestamps,
current limit, elapsed time, and any reservation with the vendor app on a real
charger. The packet fixtures are synthetic, not claimed device captures.

## Release and development notes

This change prepares library **0.4.7** and pins the custom integration to that
version. **Publish `library-v0.4.7` to PyPI before merging/distributing the new
integration dependency.** No tag or release is created by this PR, and the
HACS version is intentionally left for the maintainer's release process.
For development/tests, install this checkout with `pip install -e ".[dev]"`;
testing only the custom component against the old 0.4.6 wheel is insufficient.

The pinned Home Assistant Core baseline does not contain these entities yet.
`core-baseline.json` retains its original Core hashes and explicitly records
only the two changed integration files (`sensor.py` and `strings.json`) as
hash-checked development overrides. The alignment check remains strict for
all other source files and for the exact contents of those overrides.
The original Core sensor snapshots are retained; the additional entities have
explicit registration, state, units, and availability tests in
`tests/integration/test_session_sensors.py`.
