"""Switches: control on/off (read-only mode), humidity boost, summer night cooling."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import VitoventConfigEntry
from .const import SLOTS
from .controller import VitoventController
from .entity import VitoventEntity

# key -> (controller attribute, default, icon, category)
SWITCHES = {
    "control": ("control", False, "mdi:remote", EntityCategory.CONFIG),
    "humidity_boost": ("humidity_boost", True, "mdi:water-percent", None),
    "summer_cooling": ("summer_cooling", False, "mdi:snowflake", None),
}


async def async_setup_entry(hass: HomeAssistant, entry: VitoventConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([*(VitoventSwitch(c, key) for key in SWITCHES), *(VitoventSlotSwitch(c, n) for n in range(SLOTS))])


class VitoventSwitch(VitoventEntity, SwitchEntity, RestoreEntity):
    def __init__(self, controller: VitoventController, key: str) -> None:
        super().__init__(controller, key)
        self._field, self._default, self._attr_icon, self._attr_entity_category = SWITCHES[key]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        setattr(self.controller, self._field, last.state == "on" if last and last.state in ("on", "off") else self._default)

    @property
    def is_on(self) -> bool:
        return getattr(self.controller, self._field)

    async def async_turn_on(self, **kwargs: Any) -> None:
        setattr(self.controller, self._field, True)
        await self.controller.async_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        setattr(self.controller, self._field, False)
        await self.controller.async_refresh()


class VitoventSlotSwitch(VitoventEntity, SwitchEntity, RestoreEntity):
    """Time program window on/off."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, controller: VitoventController, n: int) -> None:
        super().__init__(controller, f"slot{n + 1}_active", translation_key="slot_active", placeholders={"n": str(n + 1)})
        self._n = n

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state in ("on", "off"):
            self.controller.slots[self._n]["active"] = last.state == "on"

    @property
    def is_on(self) -> bool:
        return self.controller.slots[self._n]["active"]

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.controller.slots[self._n]["active"] = True
        await self.controller.async_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.controller.slots[self._n]["active"] = False
        await self.controller.async_refresh()
