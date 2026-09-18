"""Regression tests for session and reservation telemetry."""

from datetime import datetime

from besen.exceptions import ProtocolError
from besen.models import ChargeStatus
from besen.protocol import (
    PARSERS,
    build_command,
    bytes_to_timestamp,
    parse_packet,
    parse_single_ac_charging_status,
)
import pytest


@pytest.mark.parametrize("command", [5, 6])
@pytest.mark.parametrize("extra_bytes", [0, 8])
def test_session_report_fields(command: int, extra_bytes: int) -> None:
    """Both report types decode independent fields and accept trailing extensions."""
    payload = bytearray(74 + extra_bytes)
    payload[20:22] = (180).to_bytes(2, "big")
    payload[26:30] = (1_789_747_200).to_bytes(4, "big")
    payload[46] = 16
    payload[47:51] = (1_789_750_800).to_bytes(4, "big")
    payload[51:55] = (3661).to_bytes(4, "big")
    payload[55:59] = (10000).to_bytes(4, "big")
    payload[59:63] = (10456).to_bytes(4, "big")
    payload[63:67] = (456).to_bytes(4, "big")

    packet = parse_packet(build_command(12345678, "123456", command, payload))
    values = PARSERS[packet.command](packet.data, packet.identifier)

    assert values == {
        "session_energy": 4.56,
        "session_start": datetime.fromisoformat(bytes_to_timestamp(1_789_750_800)),
        "session_duration": 3661,
        "session_current_limit": 16,
        "reservation_start": datetime.fromisoformat(bytes_to_timestamp(1_789_747_200)),
        "reservation_duration": 180,
    }
    status = ChargeStatus(power=3500, total_energy=104.56).updated(**values)
    assert status.session_start is not None
    assert status.session_start.utcoffset() is not None
    assert status.reservation_start is not None
    assert status.reservation_start.utcoffset() is not None
    assert status.power == 3500
    assert status.total_energy == 104.56


@pytest.mark.parametrize("sentinel", [0, 0xFFFFFFFF])
def test_unset_session_timestamps(sentinel: int) -> None:
    """Unset timestamps must not appear as dates in 1970 or 2106."""
    payload = bytearray(74)
    payload[26:30] = sentinel.to_bytes(4, "big")
    payload[47:51] = sentinel.to_bytes(4, "big")
    values = parse_single_ac_charging_status(bytes(payload), "")
    assert values["session_start"] is None
    assert values["reservation_start"] is None


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [(0, None), (65535, None), (1, 1), (180, 180), (65534, 65534)],
)
def test_reservation_duration(minutes: int, expected: int | None) -> None:
    """The reservation limit is minutes, with unset/unlimited values unknown."""
    payload = bytearray(74)
    payload[20:22] = minutes.to_bytes(2, "big")
    assert parse_single_ac_charging_status(bytes(payload), "")[
        "reservation_duration"
    ] == expected


@pytest.mark.parametrize(
    ("amps", "expected"), [(0, None), (255, None), (6, 6), (16, 16), (32, 32), (80, 80)]
)
def test_session_current_limit(amps: int, expected: int | None) -> None:
    """Read the session limit without substituting the configured current limit."""
    payload = bytearray(74)
    payload[46] = amps
    assert parse_single_ac_charging_status(bytes(payload), "")[
        "session_current_limit"
    ] == expected


@pytest.mark.parametrize(
    ("seconds", "expected"), [(0, 0), (3661, 3661), (0xFFFFFFFF, None)]
)
def test_session_duration(seconds: int, expected: int | None) -> None:
    """Reported elapsed seconds preserve zero and reject the all-ones sentinel."""
    payload = bytearray(74)
    payload[51:55] = seconds.to_bytes(4, "big")
    assert parse_single_ac_charging_status(bytes(payload), "")[
        "session_duration"
    ] == expected


@pytest.mark.parametrize("length", [0, 20, 46, 50, 54, 63, 73])
def test_session_report_rejects_truncation(length: int) -> None:
    """Do not turn incomplete fields into misleading zero readings."""
    with pytest.raises(ProtocolError, match="shorter than 74 bytes"):
        parse_single_ac_charging_status(bytes(length), "")


def test_empty_report_clears_previous_session() -> None:
    """A subsequent empty report clears optional fields instead of retaining them."""
    old = ChargeStatus(
        power=3500,
        session_start=datetime.fromisoformat("2026-09-18T12:00:00+00:00"),
        session_duration=3661,
        session_current_limit=16,
        reservation_start=datetime.fromisoformat("2026-09-18T11:00:00+00:00"),
        reservation_duration=180,
    )
    cleared = old.updated(**parse_single_ac_charging_status(bytes(74), ""))
    assert cleared.session_start is None
    assert cleared.session_duration == 0
    assert cleared.session_current_limit is None
    assert cleared.reservation_start is None
    assert cleared.reservation_duration is None
    assert cleared.session_energy == 0
    assert cleared.power == 3500
    assert old.session_duration == 3661


def test_session_fields_are_unknown_before_first_report() -> None:
    """Backward-compatible model defaults do not imply a session exists."""
    status = ChargeStatus()
    assert status.session_start is None
    assert status.session_duration is None
    assert status.session_current_limit is None
    assert status.reservation_start is None
    assert status.reservation_duration is None
