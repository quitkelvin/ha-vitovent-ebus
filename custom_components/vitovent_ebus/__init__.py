"""Viessmann Vitovent 300-W (Brink Renovent Excellent) control via ebusd/MQTT."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .controller import VitoventController

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT, Platform.SWITCH, Platform.BUTTON, Platform.TIME, Platform.NUMBER]

type VitoventConfigEntry = ConfigEntry[VitoventController]


async def async_setup_entry(hass: HomeAssistant, entry: VitoventConfigEntry) -> bool:
    controller = VitoventController(hass, entry)
    try:
        await controller.async_start()
    except RuntimeError as err:
        raise ConfigEntryNotReady(str(err)) from err
    entry.runtime_data = controller
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VitoventConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_stop()
    return ok


async def _options_updated(hass: HomeAssistant, entry: VitoventConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
