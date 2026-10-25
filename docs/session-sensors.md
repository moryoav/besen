# Session sensors

The custom integration reports timing and limits for the current or most
recently completed charging session, alongside Session energy and the last
observed stop reason. These sensors support single- and three-phase chargers.

| Entity name | Native value | Default | Meaning |
| --- | --- | --- | --- |
| Session start | Timestamp | Enabled | When the charger started the session. Power delivery can begin later. Attributes contain `session_id` and `started_by`. |
| Last session stop reason | Enum | Enabled | Why the last session observed by this client ended. Attributes contain `session_id`, `started_by`, `stopped_by`, `stop_reason_code`, `started_at` and `ended_at`. |
| Session duration | Seconds | Enabled | Elapsed session time reported by the charger, not a locally running timer. |
| Session current limit | Amperes | Disabled | Current limit recorded for the session, separate from the **Charging current** setting. |
| Scheduled start | Timestamp | Disabled | Start time of a scheduled (delayed) session. For an immediate start, the time the start was requested. Unknown unless a schedule is pending or a session is running. |
| Charging time limit | Minutes | Disabled | Time after which the charger ends the session. Unknown when there is no limit, and unless a schedule is pending or a session is running. |

Enable the disabled sensors from the charger's device page if you use them.
Sessions started with the **Charge** switch are immediate and set no time limit,
so their Scheduled start is the time of the start request and Charging time
limit stays unknown. A scheduled start or a time limit appears when one is set
with the [Start charging action](scheduled-charging.md), available from HACS
0.5.10, or elsewhere, such as in the vendor app. The charger firmware calls a
scheduled start a "reservation".

The last reported values remain after a session ends, except for Scheduled start
and Charging time limit. The charger keeps reporting those two after a schedule
is cancelled or a session has finished, so from HACS 0.5.11 they are shown only
while a schedule is pending or a session is running. The sensors are unknown
before the first session report. Zero duration remains a valid zero; unset
timestamps and unset or unlimited limits are unknown instead of dates or large
numbers. A later report without these values clears them. All sensors become
unavailable when the connection or authentication is lost. The sensors add no
polling and no charging commands.

## Session source and stop reason

**Last session stop reason** reports readable states such as **Stopped by
software**, **Stopped by button**, **Car finished charging** and **Cable
unplugged**. It is separate from the active session and does not replace Session
energy or Session duration. An unknown numeric reason is shown as **Unrecognized
reason**, with the original code in `stop_reason_code`.

The starter and stopper are the identities reported by the firmware. For
example, `Key` is the button identity and `evseMQTT` is the Python client's
identity. Another value may identify a phone or card. A reported identity does
not establish a person's name or prove a physical button press; the stop-reason
code provides the firmware's explanation. These identifiers are visible locally
in entity attributes and redacted from diagnostic downloads.

The last reason is unknown until a `0x0009` end record arrives. A new client
after a reload or restart begins with no last record. The same client retains
its last observed record during a reconnect, with entities unavailable while
disconnected. Stops missed while disconnected and the charger's historical
replay are not recovered. Cached data is the last observed end, not a claim
that no newer session ended elsewhere.

Two sessions can have the same reason and ID. The record times distinguish
them. For an automation that needs every observed end, trigger on the sensor's
`ended_at` attribute changing, rather than only a change of its reason state.
Times use the existing library timestamp interpretation; phone-app clock
adjustments can affect how firmware times compare with local wall time.

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

The companion `besen` 0.7.0 API supplies session identity from live/completed
reports and the end reason and start/end times from `0x0009`. It filters
duplicate and interleaved copies using a bounded cache, including record times
so reused IDs do not hide another session. This integration adds no charger
commands. Protocol and integration tests use synthetic data checked against
the native app layout; physical validation of this implementation is pending.

## Development notes

HACS 0.5.9 adds these sensors. HACS 0.5.13 requires library 0.4.11 or later,
which clears inactive schedule values and ignores stale session reports.
The integration reads these normalized values directly.
HACS 0.5.14 requires library 0.5.0 or later and reads its corrected `Scheduled`
charging status directly; the Home Assistant sensor still reports `scheduled`.
Update through HACS and restart Home Assistant to upgrade both together.
For development and tests, install the dependencies as described in
[CONTRIBUTING.md](../CONTRIBUTING.md#development-setup).

The pinned Home Assistant Core baseline does not contain these sensors yet.
`core-baseline.json` retains its original Core hashes, records `sensor.py` as a
hash-checked development override, and extends the existing `strings.json`
override with the five sensor names. The alignment check remains strict for all
other source files and for the exact contents of those overrides.
