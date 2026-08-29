"""Tests for Besen data models."""

from __future__ import annotations

from besen.models import (
    BesenData,
    ChargerConfig,
    ChargerInfo,
    ChargeStatus,
    CommandResult,
)


def test_data_models_are_immutable_and_updatable() -> None:
    """Model update helpers return changed copies."""

    info = ChargerInfo(address="AA:BB", model="BS20")
    config = ChargerConfig(charge_amps=6)
    charge = ChargeStatus(
        charger_status=False,
        power=3200,
        total_energy=123.45,
        session_energy=4.2,
    )
    command = CommandResult(command="charge_start", values={"output_amps": 6})
    data = BesenData(
        info=info,
        config=config,
        charge=charge,
        last_command=command,
    )

    updated = data.updated(
        info=info.updated(serial="1234"),
        config=config.updated(charge_amps=10),
        charge=charge.updated(charger_status=True),
        available=True,
    )

    assert data.info.serial is None
    assert updated.info.serial == "1234"
    assert updated.config.charge_amps == 10
    assert updated.charge.charger_status is True
    assert updated.charge.power == 3200
    assert updated.charge.total_energy == 123.45
    assert updated.charge.session_energy == 4.2
    assert updated.available is True
    assert updated.last_command == command
