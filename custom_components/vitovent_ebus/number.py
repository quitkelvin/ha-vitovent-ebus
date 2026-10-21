"""Unit parameters (air volume per stage, imbalance) and the adjustable limits / air volumes of the stage logic."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VitoventConfigEntry
from .const import CONF_BATH_LIMIT, CONF_CO2_LIMIT, CONF_COOKING_WATTS, CONF_ROOM_LIMIT, PARAM_MESSAGES
from .controller import VitoventController
from .entity import VitoventEntity

# key -> (min, max, step, unit, icon); limits replace the start values from the options while the entity exists
LIMITS = {
    CONF_BATH_LIMIT: (40, 100, 1, "%", "mdi:water-percent-alert"),
    CONF_ROOM_LIMIT: (40, 100, 1, "%", "mdi:water-percent"),
    CONF_CO2_LIMIT: (400, 3000, 50, "ppm", "mdi:molecule-co2"),
    CONF_COOKING_WATTS: (100, 5000, 50, "W", "mdi:stove"),
}
# air volumes used in eco mode: eco/reduced share the unit stage Reduced, high/max the unit stage High
FLOWS = {
    "flow_eco": (50, 150, 5, "mdi:leaf"),
    "flow_reduced": (50, 250, 5, "mdi:fan-chevron-down"),
    "flow_high": (150, 400, 5, "mdi:fan-chevron-up"),
    "flow_max": (200, 400, 5, "mdi:fan-plus"),
}


async def async_setup_entry(hass: HomeAssistant, entry: VitoventConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([*(VitoventParameter(c, name, spec) for name, spec in PARAM_MESSAGES.items()),
                        *(VitoventLimit(c, key) for key in LIMITS),
                        *(VitoventFlow(c, key) for key in FLOWS)])


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


class _Stored(VitoventEntity, RestoreNumber):
    """A value of the stage logic, kept in Home Assistant (nothing is written to the unit)."""

    _attr_mode = NumberMode.SLIDER

    def _get(self) -> float:
        raise NotImplementedError

    def _set(self, value: float) -> None:
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            self._set(float(last.native_value))

    @property
    def native_value(self) -> float:
        return self._get()

    async def async_set_native_value(self, value: float) -> None:
        self._set(float(value))
        await self.controller.async_refresh()


class VitoventLimit(_Stored):
    def __init__(self, controller: VitoventController, key: str) -> None:
        super().__init__(controller, key, translation_key=f"limit_{key}")
        self._key = key
        (self._attr_native_min_value, self._attr_native_max_value, self._attr_native_step,
         self._attr_native_unit_of_measurement, self._attr_icon) = LIMITS[key]

    def _get(self) -> float:
        return self.controller.limits[self._key]

    def _set(self, value: float) -> None:
        self.controller.limits[self._key] = value


class VitoventFlow(_Stored):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = "m³/h"

    def __init__(self, controller: VitoventController, key: str) -> None:
        super().__init__(controller, f"target_{key}")  # unit parameters use flow_* already
        self._key = key
        self._attr_native_min_value, self._attr_native_max_value, self._attr_native_step, self._attr_icon = FLOWS[key]

    def _get(self) -> float:
        return self.controller.flows[self._key]

    def _set(self, value: float) -> None:
        self.controller.flows[self._key] = int(value)
