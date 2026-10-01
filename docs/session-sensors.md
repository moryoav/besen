# Session sensors

The custom integration adds five read-only sensors for the current or most
recently completed charging session, alongside Session energy. They are created
for single- and three-phase chargers.

| Entity name | Native value | Default | Meaning |
| --- | --- | --- | --- |
| Session start | Timestamp | Enabled | When the charger started the session. Power delivery can begin later. |
| Session duration | Seconds | Enabled | Elapsed session time reported by the charger, not a locally running timer. |
| Session current limit | Amperes | Disabled | Current limit recorded for the session, separate from the **Charging current** setting. |
| Scheduled start | Timestamp | Disabled | Start time of a scheduled (delayed) session. For an immediate start, the time the start was requested. |
| Charging time limit | Minutes | Disabled | Time after which the charger ends the session. Unknown when there is no limit. |

Enable the disabled sensors from the charger's device page if you use them.
Sessions started from Home Assistant are immediate and set no time limit, so
their Scheduled start is the time of the start request and Charging time limit
stays unknown. A scheduled start or a time limit appears only when one is set
elsewhere, such as in the vendor app. The charger firmware calls a scheduled
start a "reservation".

The last reported values remain after a session ends. The sensors are unknown
before the first session report. Zero duration remains a valid zero; unset
timestamps and unset or unlimited limits are unknown instead of dates or large
numbers. A later report without these values clears them. All sensors become
unavailable when the connection or authentication is lost. No scheduling
controls, additional polling, or charging commands are added.

## Protocol and validation

The existing parser handles both current (`0x0005`) and completed (`0x0006`)
session reports, requiring at least 74 payload bytes. Session energy decoding
and the existing electrical and status sensors are unchanged.

| Field | Payload bytes (zero-based, end exclusive) |
| --- | --- |
| Charging time limit, minutes | `[20:22]` |
| Scheduled start timestamp | `[26:30]` |
| Session current limit | `[46:47]` |
| Session start timestamp | `[47:51]` |
| Elapsed duration, seconds | `[51:55]` |
| Session energy (existing) | `[63:67]` |

The field layout was cross-checked against
[EVSEMaster's parser](https://github.com/RafaelSchridi/evsemaster/blob/main/evsemaster/protocol.py).
Timestamps are decoded as UTC Unix epochs and returned to Home Assistant as
timezone-aware datetime values. This is the format the library writes when it
syncs the charger clock and requests charging, so a written time decodes to the
same instant. The older `bytes_to_timestamp` helper shifts values by eight hours
minus the local UTC offset and is not used for these sensors. Clock
synchronization is unchanged, and EVSEMaster's per-device clock-skew
compensation is not added. A session started while the vendor app, rather than
Besen, last set the charger clock may therefore show an offset time.

Library tests cover both report types, packet framing, extended and truncated
payloads, sentinel values, timestamp round trips, and model merging. The Home
Assistant tests add the sensors to the sensor platform snapshots and cover push
updates and the disabled-by-default sensors. The packet fixtures are synthetic,
not device captures. Compare the timestamps, elapsed time, current limit, and
any scheduled start with the vendor app on a real charger.

## Development notes

HACS 0.5.9 adds these sensors. Library 0.4.8 provides the fields, and the
custom integration requires it.
For development and tests, install the dependencies as described in
[CONTRIBUTING.md](../CONTRIBUTING.md#development-setup).

The pinned Home Assistant Core baseline does not contain these sensors yet.
`core-baseline.json` retains its original Core hashes, records `sensor.py` as a
hash-checked development override, and extends the existing `strings.json`
override with the five sensor names. The alignment check remains strict for all
other source files and for the exact contents of those overrides.
