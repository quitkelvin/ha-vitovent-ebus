"""Unit parameters: air volume per stage and permanent imbalance (installer level of the unit)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VitoventConfigEntry
from .const import PARAM_MESSAGES
from .controller import VitoventController
from .entity import VitoventEntity


async def async_setup_entry(hass: HomeAssistant, entry: VitoventConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities(VitoventParameter(c, name, spec) for name, spec in PARAM_MESSAGES.items())


class VitoventParameter(VitoventEntity, NumberEntity):
    """Value is read from the unit; writing needs the switch 'Control' (read only otherwise)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "m³/h"

    def __init__(self, controller: VitoventController, name: str, spec: dict) -> None:
        super().__init__(controller, spec["key"])
        self._msg = name
        self._attr_native_min_value = spec["min"]
        self._attr_native_max_value = spec["max"]
        self._attr_native_step = spec["step"]
        self._attr_icon = "mdi:scale-unbalanced" if spec["key"] == "imbalance" else "mdi:fan-chevron-down"

    @property
    def native_value(self) -> float | None:
        return self.controller.number(self._msg)

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.async_set_parameter(self._msg, value)
