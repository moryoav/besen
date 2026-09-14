"""Adapt legacy HACS entries to the Core integration's identifiers."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er, issue_registry as ir

from .const import DOMAIN


@callback
def async_migrate_legacy_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Preserve existing installations when moving to Core behavior."""

    if CONF_NAME not in entry.data:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_NAME: entry.title}
        )
    if "sync_clock" in entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={
                key: value
                for key, value in entry.options.items()
                if key != "sync_clock"
            },
        )

    registry = er.async_get(hass)
    address = entry.data[CONF_ADDRESS]
    old_id = registry.async_get_entity_id("number", DOMAIN, f"{address}_charge_amps")
    new_id = registry.async_get_entity_id(
        "number", DOMAIN, f"{address}_charging_current"
    )
    if old_id is not None and new_id is None:
        old_entry = registry.async_get(old_id)
        if old_entry is not None and old_entry.config_entry_id == entry.entry_id:
            registry.async_update_entity(
                old_id, new_unique_id=f"{address}_charging_current"
            )

    for key in ("no_connectable_path", "reauth_required"):
        ir.async_delete_issue(hass, DOMAIN, f"{entry.entry_id}_{key}")
