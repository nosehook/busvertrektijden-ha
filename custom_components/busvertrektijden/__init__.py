from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .bus import Bus
from .const import CONF_FILTERS, CONF_SHORT_NAME_FILTER, CONF_STOP_NAME, DOMAIN
from .coordinator import BusCoordinator

PLATFORMS = [Platform.SENSOR]


def valid_unique_ids(entry: ConfigEntry) -> set[str]:
    stop = entry.data[CONF_STOP_NAME]
    ids = {stop, f"{stop}_next_minutes", f"{stop}_next_time"}
    for flt in entry.options.get(CONF_FILTERS, []):
        ids |= {f"{stop}_{flt['id']}_minutes", f"{stop}_{flt['id']}_time"}
    return ids


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bus vertrektijden from a config entry."""
    bus = Bus(entry.data[CONF_STOP_NAME], entry.data.get(CONF_SHORT_NAME_FILTER))
    coordinator = BusCoordinator(hass, bus)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Remove sensors of filters that were deleted in the options
    registry = er.async_get(hass)
    keep = valid_unique_ids(entry)
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        if ent.unique_id not in keep:
            registry.async_remove(ent.entity_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Bus vertrektijden entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
