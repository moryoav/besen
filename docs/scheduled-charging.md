# Scheduled and time-limited charging

The custom integration adds one action, **Start charging**
(`besen.start_charging`). It starts a charging session at a later time, for a
limited time, or both. The **Charge** switch keeps starting a session now, with
no time limit.

## The action

The action targets the charger's **Charge** switch.

| Field | Selector | Meaning |
| --- | --- | --- |
| `start` | Date and time | When the charger starts charging, at most 24 hours ahead. A time without a UTC offset is in the Home Assistant time zone. Without it, charging starts now. |
| `duration` | Duration | How long the charger charges before it ends the session, in whole minutes, from 1 minute to 65534 minutes. Without it, there is no time limit. |

```yaml
action: besen.start_charging
target:
  entity_id: switch.garage_charge
data:
  start: "2026-10-02 01:00:00"
  duration:
    hours: 3
```

The schedule is stored on the charger, which the firmware calls a
"reservation". The action waits for the charger's reply, like the **Charge**
switch does:

- A duration outside the supported range, or one that is not a whole number of
  minutes, is refused before anything is sent.
- A start time that is not in the future, or is more than 24 hours ahead, fails
  with a validation error.
- A rejection by the charger, a lost connection, or a missing reply fails with
  the same error as the **Charge** switch.

## What the charger does

Checked on a three-phase Besen BS20:

- The charger holds one schedule at a time and accepts it with or without a
  vehicle connected.
- While a schedule is pending, the **Charge** switch stays off, **Charging
  status** shows **Scheduled**, and **Charging message** shows **Charging
  reservation**. The **Scheduled start** and **Charging time limit** sensors
  show the accepted values while the schedule is pending or the session is
  running. See [session sensors](session-sensors.md).
- The `switch.turn_off` action on the **Charge** switch cancels a pending
  schedule. The switch is already off while a start is scheduled, so its toggle
  on a dashboard cannot send that command.
- The charger rejects a new start, scheduled or not, while a schedule is pending
  or a session is charging. Cancel the schedule or stop the session first.
- Charging starts at the scheduled time, and a time-limited session stops by
  itself when the time is up.
- A start with only a `duration` begins now, so it needs a connected vehicle.
- After a session has finished, the charger refuses an immediate start until it
  receives a stop. The library sends that stop automatically, so the **Charge**
  switch and the action work in that state.
- Every start uses the current set by **Charging current**. If the charger has
  not reported that current, the start fails instead of guessing.

## How it is built

The action is an entity action on the switch platform, registered once when the
integration is set up, in `services.py`. `services.yaml`, `strings.json`, and
`icons.json` describe it for the Home Assistant interface.

The `besen` library builds the request. Its
`async_start_charging()` takes the start time and the duration in minutes,
checks the start time, and accepts the charger's "reservation successful"
reply. The integration converts the start time to UTC and the duration to whole
minutes, and turns the library's start time error into a validation error. The
library's upper duration limit, `MAX_CHARGE_DURATION_MINUTES`, bounds the
`duration` field.

| Request payload bytes (zero-based, end exclusive) | Immediate start | Scheduled or time-limited start |
| --- | --- | --- |
| `[33:34]` | `0` | `1` when a start time is given |
| `[34:38]` | Current time | Start time, in the format the clock sync writes |
| `[40:42]` | `FF FF`, unlimited | Duration in minutes, big-endian, when given |

The layout and reply codes were cross-checked against
[EVSEMaster](https://github.com/RafaelSchridi/evsemaster/blob/main/docs/protocol.md)
and [emproto](https://github.com/johnwoo-nl/emproto). The energy limit at
`[42:44]` stays unlimited.

The tests call the action with a start time, a duration, both, and neither, with
and without a UTC offset, and check the values that reach the library. They also
cover a duration out of range, an unusable start time, and a charger rejection.

## Development notes

HACS 0.5.10 adds the action. Library 0.4.9 provides scheduled and time-limited
starts, and the custom integration requires it.

HACS 0.5.11 requires library 0.4.10, which stops a start from falling back to
the charger's maximum current, corrects the Current state names, and sends the
stop a finished session needs before an immediate start. The integration shows
the schedule sensors only while a schedule is pending or a session is running,
and renames the Charging status state `canceled` to `scheduled`; both are
recorded as changes to the `sensor.py` and `strings.json` development overrides.

The pinned Home Assistant Core baseline does not contain the action yet.
`core-baseline.json` retains its original Core hashes, records `__init__.py`,
`coordinator.py`, `switch.py`, `icons.json`, `strings.json`, and
`quality_scale.yaml` as hash-checked development overrides, and lists
`services.py` and `services.yaml` as new files. The quality scale checklist
marks `action-setup` and `docs-actions` done, because the integration now
defines a custom action.
