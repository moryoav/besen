"""Besen BLE packet protocol helpers.

The packet format and field offsets are derived from the MIT-licensed
evseMQTT project by slespersen and contributors.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Literal

from .const import (
    CHARGE_START_ERROR,
    CHARGE_START_RESERVATION,
    CHARGER_STATUS,
    CHARGING_STATUS,
    CHARGING_STATUS_DESCRIPTIONS,
    CURRENT_STATE,
    ERRORS,
    LANGUAGES,
    OUTPUT_STATE,
    PACKET_HEADER,
    PACKET_MIN_LENGTH,
    PLUG_STATE,
    STOP_REASON,
    TEMPERATURE_UNITS,
)
from .exceptions import ProtocolError


@dataclass(slots=True, frozen=True)
class ParsedPacket:
    """Decoded Besen protocol packet."""

    identifier: str
    password: bytes
    command: int
    data: bytes
    raw: bytes


def _flatten(values: Iterable[int | Iterable[int]]) -> list[int]:
    """Flatten a one-level nested integer iterable."""

    flattened: list[int] = []
    for value in values:
        if isinstance(value, int):
            flattened.append(value)
        else:
            flattened.extend(value)
    return flattened


def _serial_to_int(serial: str | int) -> int:
    """Convert the charger serial into the integer format used on the wire."""

    if isinstance(serial, int):
        return serial
    try:
        return int(serial)
    except ValueError:
        return int(serial, 16)


def build_command(
    serial: str | int,
    password: str,
    command: int,
    data: Iterable[int | Iterable[int]] | None = None,
) -> bytes:
    """Build a command packet for the charger."""

    payload = _flatten(data or [])
    if any(byte < 0 or byte > 255 for byte in payload):
        raise ProtocolError("Command payload contains bytes outside 0..255")

    length = PACKET_MIN_LENGTH + len(payload)
    packet = bytearray()
    packet.extend(PACKET_HEADER)
    packet.extend(struct.pack(">H", length))
    packet.append(0)
    packet.extend(struct.pack("<Q", _serial_to_int(serial)))
    packet.extend(password.encode("ascii"))
    packet.extend(struct.pack(">H", command))
    packet.extend(payload)
    checksum = sum(packet) % 0xFFFF
    packet.extend(struct.pack(">H", checksum))
    packet.extend(b"\x0f\x02")
    return bytes(packet)


def parse_packet(packet: bytes | bytearray) -> ParsedPacket:
    """Parse and validate a complete packet."""

    raw = bytes(packet)
    if len(raw) < PACKET_MIN_LENGTH:
        raise ProtocolError("Packet is shorter than the minimum length")
    if raw[:2] != PACKET_HEADER:
        raise ProtocolError("Packet header is invalid")

    length = int.from_bytes(raw[2:4], "big")
    if length != len(raw):
        raise ProtocolError(
            f"Packet length mismatch: expected {length}, got {len(raw)}"
        )
    if raw[-2:] != b"\x0f\x02":
        raise ProtocolError("Packet footer is invalid")

    checksum = int.from_bytes(raw[-4:-2], "big")
    calculated = sum(raw[:-4]) % 0xFFFF
    if checksum != calculated:
        raise ProtocolError("Packet checksum is invalid")

    return ParsedPacket(
        identifier=bytes_to_hex(raw[5:13]),
        password=raw[13:19],
        command=int.from_bytes(raw[19:21], "big"),
        data=raw[21:-4],
        raw=raw,
    )


class PacketAssembler:
    """Reassemble fragmented BLE notifications into complete packets."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes | bytearray) -> list[ParsedPacket]:
        """Feed a notification chunk and return all complete packets."""

        self._buffer.extend(chunk)
        packets: list[ParsedPacket] = []

        while self._buffer:
            header_index = self._buffer.find(PACKET_HEADER)
            if header_index == -1:
                self._buffer.clear()
                break
            if header_index:
                del self._buffer[:header_index]
            if len(self._buffer) < 4:
                break

            length = int.from_bytes(self._buffer[2:4], "big")
            if length < PACKET_MIN_LENGTH:
                del self._buffer[:2]
                continue
            if len(self._buffer) < length:
                break

            raw = bytes(self._buffer[:length])
            del self._buffer[:length]
            packets.append(parse_packet(raw))

        return packets


def bytes_to_hex(value: bytes | bytearray) -> str:
    """Return uppercase hex bytes without separators."""

    return "".join(f"{byte:02X}" for byte in value)


def byte_to_integer(value: int) -> int:
    """Convert a byte to an unsigned integer."""

    return value & 0xFF


def bytes_to_integer(
    value: bytes | bytearray,
    byteorder: Literal["big", "little"] = "big",
) -> int:
    """Convert bytes to an unsigned integer."""

    return int.from_bytes(value, byteorder=byteorder)


def bytes_to_int_little(value: bytes | bytearray) -> int:
    """Convert Besen's mixed little-endian 4-byte integer."""

    if len(value) < 4:
        return 0
    return (
        (value[3] & 0xFF)
        | ((value[0] & 0xFF) << 24)
        | ((value[1] & 0xFF) << 16)
        | ((value[2] & 0xFF) << 8)
    )


def bytes_to_long_little(value: bytes | bytearray) -> int:
    """Convert Besen's mixed little-endian long."""

    return bytes_to_int_little(value) & 0xFFFFFFFF


def get_phases(charger_type: int) -> int:
    """Return phase count inferred from charger type."""

    return 3 if charger_type in {10, 11, 12, 13, 14, 15, 22, 23, 24, 25} else 1


def safe_decode(value: bytes | bytearray) -> str:
    """Decode null-padded text fields."""

    return bytes(value).strip(b"\x00").decode("utf-8", errors="replace").strip()


def shanghai_adjusted_timestamp() -> int:
    """Return the timestamp format expected by the charger."""

    shanghai_time = datetime.now(timezone(timedelta(hours=8)))
    local_time = shanghai_time.astimezone()
    return int(local_time.timestamp())


def timestamp_bytes() -> list[int]:
    """Return current timestamp as command bytes."""

    return list(shanghai_adjusted_timestamp().to_bytes(4, byteorder="big"))


def bytes_to_timestamp(value: int) -> str:
    """Convert the charger's timestamp into local ISO format."""

    shanghai_time = datetime.fromtimestamp(value, UTC) + timedelta(hours=8)
    local_offset = datetime.now().astimezone().utcoffset() or timedelta()
    return (shanghai_time - local_offset).isoformat()


def bytes_to_timezoned_epoch(value: int) -> int:
    """Convert the charger's timestamp into local epoch seconds."""

    shanghai_time = datetime.fromtimestamp(value, UTC) + timedelta(hours=8)
    local_offset = datetime.now().astimezone().utcoffset() or timedelta()
    return int((shanghai_time - local_offset).timestamp())


def device_name_bytes(name: str) -> list[int]:
    """Return a padded ACP device name."""

    encoded = bytearray(f"ACP#{name}".encode("ascii", errors="ignore"))
    if len(encoded) > 15:
        encoded = encoded[:15]
    else:
        encoded.extend([32] * (15 - len(encoded)))
    encoded.extend([0] * (32 - len(encoded)))
    return list(encoded)


def generate_charge_id() -> list[int]:
    """Generate the 16-byte charge ID used for app-initiated charging."""

    encoded = (datetime.now(UTC).astimezone().strftime("%Y%m%d%H%M") + "1337").encode(
        "ascii"
    )
    return list(encoded.ljust(16, b"\x00"))


def convert_temperature(temp_c: float) -> float:
    """Convert Celsius to Fahrenheit."""

    return round(temp_c * 9 / 5 + 32, 2)


def get_failure_details(error_info: str) -> str:
    """Return a human-readable error from the bit field."""

    return ERRORS.get(error_info.find("1"), "No Error")


def charging_status(plug_state: int | None, current_state: int | None) -> int | None:
    """Map plug/current state into a charging status code."""

    if plug_state is None or current_state is None:
        return None
    if current_state == 1:
        return 8
    if current_state in (2, 3):
        return 11
    if current_state == 10:
        return 9
    if current_state == 11:
        return 10
    if current_state == 12:
        return 7
    if current_state == 13:
        return 1
    if current_state == 14:
        return 2 if plug_state == 4 else 3 if plug_state == 2 else None
    if current_state == 15 and plug_state in (4, 2):
        return 4
    if current_state == 17:
        return 5
    if current_state == 20:
        return 6
    return None


def key_by_value(dictionary: dict[str, int], target_value: int) -> str | None:
    """Return the first key for a dictionary value."""

    return next(
        (key for key, value in dictionary.items() if value == target_value),
        None,
    )


def parse_login(data: bytes, identifier: str) -> dict[str, Any]:
    """Parse login beacon/response data."""

    charger_type = byte_to_integer(data[0])
    return {
        "serial": identifier,
        "charger_type": charger_type,
        "phases": get_phases(charger_type),
        "manufacturer": safe_decode(data[1:16]),
        "model": safe_decode(data[17:32]),
        "hardware_version": safe_decode(data[33:49]),
        "output_power": bytes_to_int_little(data[49:53]),
        "output_max_amps": byte_to_integer(data[53]),
        "support": safe_decode(data[54:69]),
    }


def parse_version(data: bytes, _identifier: str) -> dict[str, Any]:
    """Parse version response."""

    return {
        "hardware_version": safe_decode(data[0:15]),
        "software_version": safe_decode(data[16:31]),
        "feature": bytes_to_long_little(data[32:36]),
    }


def parse_single_ac_status(data: bytes, _identifier: str) -> dict[str, Any]:
    """Parse live single/three-phase AC status."""

    if len(data) < 25:
        error_info = f"{int(data[21]):08b}{int(data[22]):08b}"
    else:
        error_info = (
            f"{int(data[21]):08b}{int(data[22]):08b}"
            f"{int(data[23]):08b}{int(data[24]):08b}"
        )
    plug_state_code = byte_to_integer(data[18])
    current_state_code = byte_to_integer(data[20])
    status_code = charging_status(plug_state_code, current_state_code)
    inner_raw = bytes_to_integer(data[13:15])
    inner_temp_c = -1.0 if inner_raw == 255 else round((inner_raw - 20000) * 0.01, 1)

    status: dict[str, Any] = {
        "line_id": bytes_to_integer(data[0:1]),
        "error_info": error_info,
        "error_details": get_failure_details(error_info),
        "l1_voltage": round(bytes_to_integer(data[1:3]) * 0.1, 1),
        "l1_amperage": round(bytes_to_integer(data[3:5]) * 0.01, 1),
        "total_energy": round(bytes_to_int_little(data[5:9]) / 1000, 2),
        "current_amount": round(bytes_to_integer(data[9:13]) * 0.01, 1),
        "inner_temp_c": inner_temp_c,
        "inner_temp_f": convert_temperature(inner_temp_c),
        "outer_temp": (
            -1.0
            if bytes_to_integer(data[15:17]) == 255
            else round((bytes_to_integer(data[15:17]) - 20000) * 0.01, 1)
        ),
        "emergency_btn_state": byte_to_integer(data[17]),
        "plug_state": _safe_list_value(PLUG_STATE, plug_state_code),
        "output_state": _safe_list_value(OUTPUT_STATE, byte_to_integer(data[19])),
        "current_state": _safe_list_value(CURRENT_STATE, current_state_code),
        "new_protocol": len(data) > 33,
        "charging_status": CHARGING_STATUS.get(status_code or 0),
        "charging_status_description": CHARGING_STATUS_DESCRIPTIONS.get(
            status_code or 0
        ),
        "charger_status": bool(CHARGER_STATUS.get(status_code or 0, 0)),
    }

    l1_power = status["l1_voltage"] * status["l1_amperage"]
    status["current_energy"] = l1_power if l1_power else 0

    if len(data) > 33:
        status["l2_voltage"] = round(bytes_to_integer(data[25:27]) * 0.1, 1)
        status["l2_amperage"] = round(bytes_to_integer(data[27:29]) * 0.01, 1)
        status["l3_voltage"] = round(bytes_to_integer(data[29:31]) * 0.1, 1)
        status["l3_amperage"] = round(bytes_to_integer(data[31:33]) * 0.01, 1)
        status["current_energy"] = round(
            l1_power
            + status["l2_voltage"] * status["l2_amperage"]
            + status["l3_voltage"] * status["l3_amperage"]
        )

    return status


def parse_output_amps(data: bytes, _identifier: str) -> dict[str, Any]:
    """Parse charge amps config."""

    return {"charge_amps": byte_to_integer(data[1])}


def parse_name(data: bytes, _identifier: str) -> dict[str, Any]:
    """Parse configured charger name."""

    return {"device_name": safe_decode(data[1:32].replace(b"\x00", b""))}


def parse_system_time(data: bytes, _identifier: str) -> dict[str, Any]:
    """Parse charger time."""

    epoch = bytes_to_int_little(data[1:5])
    return {
        "system_time": bytes_to_timestamp(epoch),
        "system_time_raw": bytes_to_timezoned_epoch(epoch),
    }


def parse_system_language(data: bytes, _identifier: str) -> dict[str, Any]:
    """Parse configured app language."""

    return {"language": key_by_value(LANGUAGES, byte_to_integer(data[1]))}


def parse_temperature_unit(data: bytes, _identifier: str) -> dict[str, Any]:
    """Parse configured temperature unit."""

    return {
        "temperature_unit": key_by_value(
            TEMPERATURE_UNITS,
            byte_to_integer(data[1]),
        )
    }


def parse_charge_start(data: bytes, _identifier: str) -> dict[str, Any]:
    """Parse charge start response."""

    return {
        "line_id": byte_to_integer(data[0]),
        "reservation_result": CHARGE_START_RESERVATION.get(byte_to_integer(data[1])),
        "start_result": byte_to_integer(data[2]),
        "error_reason": CHARGE_START_ERROR.get(byte_to_integer(data[3])),
        "output_amps": byte_to_integer(data[4]),
    }


def parse_charge_stop(data: bytes, _identifier: str) -> dict[str, Any]:
    """Parse charge stop response."""

    return {
        "line_id": byte_to_integer(data[0]),
        "stop_result": STOP_REASON.get(byte_to_integer(data[1])),
        "error_reason": byte_to_integer(data[2]),
    }


def _safe_list_value(values: list[str], index: int) -> str:
    """Return a list value with a fallback for unknown device values."""

    if 0 <= index < len(values):
        return values[index]
    return f"Unknown {index}"


PARSERS = {
    1: parse_login,
    2: parse_login,
    4: parse_single_ac_status,
    5: lambda data, identifier: {},
    6: lambda data, identifier: {},
    7: parse_charge_start,
    8: parse_charge_stop,
    13: parse_single_ac_status,
    257: parse_system_time,
    262: parse_version,
    263: parse_output_amps,
    264: parse_name,
    271: parse_system_language,
    274: parse_temperature_unit,
}
