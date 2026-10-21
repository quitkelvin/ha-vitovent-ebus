"""Mode select (Auto or a fixed stage)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import VitoventConfigEntry
from .const import DAY_OPTIONS, MODES, SLOTS, STAGES
from .controller import VitoventController
from .entity import VitoventEntity


async def async_setup_entry(hass: HomeAssistant, entry: VitoventConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([VitoventMode(c, "mode"),
                        *(VitoventSlotSelect(c, n, f) for n in range(SLOTS) for f in ("days", "stage"))])


class VitoventMode(VitoventEntity, SelectEntity, RestoreEntity):
    _attr_options = MODES
    _attr_icon = "mdi:fan"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state in MODES:
            self.controller.mode = last.state

    @property
    def current_option(self) -> str:
        return self.controller.mode

    async def async_select_option(self, option: str) -> None:
        self.controller.mode = option
        await self.controller.async_refresh()


class VitoventSlotSelect(VitoventEntity, SelectEntity, RestoreEntity):
    """Days (daily, Mon–Fri, Sat–Sun or one weekday) and stage of a time program window."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller: VitoventController, n: int, field: str) -> None:
        super().__init__(controller, f"slot{n + 1}_{field}", translation_key=f"slot_{field}",
                         placeholders={"n": str(n + 1)})
        self._n, self._field = n, field
        self._attr_options = DAY_OPTIONS if field == "days" else STAGES
        self._attr_icon = "mdi:calendar-week" if field == "days" else "mdi:fan-speed-2"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state in self._attr_options:
            self.controller.slots[self._n][self._field] = last.state

    @property
    def current_option(self) -> str:
        return self.controller.slots[self._n][self._field]

    async def async_select_option(self, option: str) -> None:
        self.controller.slots[self._n][self._field] = option
        await self.controller.async_refresh()
