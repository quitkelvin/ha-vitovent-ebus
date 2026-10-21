"""Buttons: 30-min boost and filter reset."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VitoventConfigEntry
from .entity import VitoventEntity


async def async_setup_entry(hass: HomeAssistant, entry: VitoventConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([VitoventBoostButton(c, "boost"), VitoventFilterResetButton(c, "filter_reset")])


class VitoventBoostButton(VitoventEntity, ButtonEntity):
    _attr_icon = "mdi:fan-plus"

    async def async_press(self) -> None:
        await self.controller.async_boost()


class VitoventFilterResetButton(VitoventEntity, ButtonEntity):
    """Only after replacing the filters: resets filter days and flow in the unit."""

    _attr_icon = "mdi:air-filter"
    _attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self.controller.async_reset_filter()
