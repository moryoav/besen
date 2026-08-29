"""Data models for Besen chargers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any


class BoardRevision(StrEnum):
    """Supported Bluetooth board revisions."""

    OLD = "old"
    REVISED = "revised"
    NEW = "new"


@dataclass(slots=True, frozen=True)
class CharacteristicPair:
    """Read/write characteristic UUIDs for a board revision."""

    read_uuid: str
    write_uuid: str
    board_revision: BoardRevision


@dataclass(slots=True, frozen=True)
class ChargerInfo:
    """Static or slowly changing charger information."""

    address: str
    serial: str | None = None
    charger_type: int | None = None
    phases: int | None = None
    manufacturer: str | None = None
    model: str | None = None
    hardware_version: str | None = None
    software_version: str | None = None
    output_power: int | None = None
    output_max_amps: int | None = None
    feature: int | None = None
    support: str | None = None
    board_revision: BoardRevision | None = None
    advertised_name: str | None = None

    def updated(self, **changes: Any) -> ChargerInfo:
        """Return a copy with changed fields."""

        return replace(self, **changes)


@dataclass(slots=True, frozen=True)
class ChargerConfig:
    """Charger configuration values reported by the device."""

    charge_amps: int | None = None
    lcd_brightness: int | None = None
    system_time: str | None = None
    system_time_raw: int | None = None
    temperature_unit: str | None = None
    language: str | None = None
    device_name: str | None = None
    rssi: int | None = None

    def updated(self, **changes: Any) -> ChargerConfig:
        """Return a copy with changed fields."""

        return replace(self, **changes)


@dataclass(slots=True, frozen=True)
class ChargeStatus:
    """Live charger status."""

    line_id: int | None = None
    error_info: str | None = None
    error_details: str | None = None
    l1_voltage: float | None = None
    l1_amperage: float | None = None
    l2_voltage: float | None = None
    l2_amperage: float | None = None
    l3_voltage: float | None = None
    l3_amperage: float | None = None
    power: int | None = None
    total_energy: float | None = None
    session_energy: float | None = None
    inner_temp_c: float | None = None
    inner_temp_f: float | None = None
    outer_temp: float | None = None
    emergency_btn_state: int | None = None
    plug_state: str | None = None
    output_state: str | None = None
    current_state: str | None = None
    new_protocol: bool | None = None
    charging_status: str | None = None
    charging_status_description: str | None = None
    charger_status: bool | None = None

    def updated(self, **changes: Any) -> ChargeStatus:
        """Return a copy with changed fields."""

        return replace(self, **changes)


@dataclass(slots=True, frozen=True)
class CommandResult:
    """Last command response from the charger."""

    command: str
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class BesenData:
    """State object exposed to Home Assistant entities."""

    info: ChargerInfo
    config: ChargerConfig = field(default_factory=ChargerConfig)
    charge: ChargeStatus = field(default_factory=ChargeStatus)
    available: bool = False
    authenticated: bool = False
    last_command: CommandResult | None = None
    last_error: str | None = None

    def updated(self, **changes: Any) -> BesenData:
        """Return a copy with changed fields."""

        return replace(self, **changes)
