"""Start/end times of the time program windows."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import VitoventConfigEntry
from .const import SLOTS
from .controller import VitoventController
from .entity import VitoventEntity


async def async_setup_entry(hass: HomeAssistant, entry: VitoventConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities(VitoventSlotTime(c, n, field) for n in range(SLOTS) for field in ("start", "end"))


class VitoventSlotTime(VitoventEntity, TimeEntity, RestoreEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller: VitoventController, n: int, field: str) -> None:
        super().__init__(controller, f"slot{n + 1}_{field}", translation_key=f"slot_{field}",
                         placeholders={"n": str(n + 1)})
        self._n, self._field = n, field
        self._attr_icon = "mdi:clock-start" if field == "start" else "mdi:clock-end"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state not in ("unknown", "unavailable"):
            try:
                self.controller.slots[self._n][self._field] = time.fromisoformat(last.state)
            except ValueError:
                pass

    @property
    def native_value(self) -> time:
        return self.controller.slots[self._n][self._field]

    async def async_set_value(self, value: time) -> None:
        self.controller.slots[self._n][self._field] = value.replace(second=0, microsecond=0)
        await self.controller.async_refresh()
