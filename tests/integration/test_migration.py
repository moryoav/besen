"""Test upgrades from the earlier HACS integration through normal setup."""

from unittest.mock import Mock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_ADDRESS, CONF_NAME, CONF_PIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)

from .conftest import FIXTURE_ADDRESS, FIXTURE_PIN, setup_integration


@pytest.mark.usefixtures("mock_besen_client")
async def test_legacy_manual_entry_upgrade(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Keep the device and charging-current entity when upgrading and reloading."""
    entry = MockConfigEntry(
        domain="besen",
        title="Garage",
        unique_id=FIXTURE_ADDRESS,
        data={CONF_ADDRESS: FIXTURE_ADDRESS, CONF_PIN: FIXTURE_PIN},
        options={"sync_clock": False},
    )
    entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("besen", FIXTURE_ADDRESS)},
        connections={(dr.CONNECTION_BLUETOOTH, FIXTURE_ADDRESS)},
    )
    old_entity = entity_registry.async_get_or_create(
        "number",
        "besen",
        f"{FIXTURE_ADDRESS}_charge_amps",
        config_entry=entry,
        device_id=device.id,
        suggested_object_id="garage_charge_amps",
    )
    entity_registry.async_update_entity(old_entity.entity_id, name="My current limit")
    ir.async_create_issue(
        hass,
        "besen",
        f"{entry.entry_id}_no_connectable_path",
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="no_connectable_path",
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data[CONF_NAME] == "Garage"
    assert entry.options == {}
    migrated = entity_registry.async_get(old_entity.entity_id)
    assert migrated is not None
    assert migrated.unique_id == f"{FIXTURE_ADDRESS}_charging_current"
    assert migrated.name == "My current limit"
    assert migrated.device_id == device.id
    assert (state := hass.states.get(old_entity.entity_id)) is not None
    assert state.state == "16"
    assert (
        ir.async_get(hass).async_get_issue(
            "besen", f"{entry.entry_id}_no_connectable_path"
        )
        is None
    )
    assert hass.states.get("select.garage_language") is None
    assert hass.states.get("number.garage_lcd_brightness") is None
    assert hass.states.get("text.garage_name") is None

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert (reloaded := entity_registry.async_get(old_entity.entity_id)) is not None
    assert reloaded.unique_id == migrated.unique_id
    assert hass.states.get(old_entity.entity_id) is not None


@pytest.mark.usefixtures("mock_besen_client")
async def test_existing_core_current_entity_is_preserved(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Do not overwrite a previously registered Core charging-current entity."""
    mock_config_entry.add_to_hass(hass)
    old_entity = entity_registry.async_get_or_create(
        "number",
        "besen",
        f"{FIXTURE_ADDRESS}_charge_amps",
        config_entry=mock_config_entry,
    )
    core_entity = entity_registry.async_get_or_create(
        "number",
        "besen",
        f"{FIXTURE_ADDRESS}_charging_current",
        config_entry=mock_config_entry,
    )
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert (retained := entity_registry.async_get(old_entity.entity_id)) is not None
    assert retained.unique_id == old_entity.unique_id
    assert hass.states.get(core_entity.entity_id) is not None


async def test_upgrade_does_not_modify_another_entry(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_besen_client: Mock,
) -> None:
    """Only migrate an entity owned by the entry being set up."""
    other_entry = MockConfigEntry(domain="besen")
    other_entry.add_to_hass(hass)
    old_entity = entity_registry.async_get_or_create(
        "number",
        "besen",
        f"{FIXTURE_ADDRESS}_charge_amps",
        config_entry=other_entry,
    )
    await setup_integration(hass, mock_config_entry)
    assert (retained := entity_registry.async_get(old_entity.entity_id)) is not None
    assert retained.unique_id == old_entity.unique_id
    mock_besen_client.async_start.assert_awaited_once()
