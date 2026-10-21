"""Config and options flow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BATH_HUMIDITY,
    CONF_BATH_LIMIT,
    CONF_CO2,
    CONF_CO2_LIMIT,
    CONF_COOKING_WATTS,
    CONF_COOLING_MONTHS,
    CONF_HEATING_MONTHS,
    CONF_INDOOR_TEMP,
    CONF_KITCHEN_POWER,
    CONF_NIGHT_END,
    CONF_NIGHT_START,
    CONF_PREFIX,
    CONF_PRESENCE,
    CONF_ROOM_HUMIDITY,
    CONF_ROOM_LIMIT,
    CONF_VACATION,
    CONF_WEEKLY_PLAN,
    DEFAULT_PREFIX,
    DEFAULTS,
    DOMAIN,
)

MONTHS = [selector.SelectOptionDict(value=str(m), label=str(m)) for m in range(1, 13)]


def _num(lo: float, hi: float, step: float, unit: str | None = None) -> selector.NumberSelector:
    return selector.NumberSelector(selector.NumberSelectorConfig(min=lo, max=hi, step=step, unit_of_measurement=unit,
                                                                 mode=selector.NumberSelectorMode.BOX))


def _ent(domain: list[str] | str, device_class: str | None = None, multiple: bool = False) -> selector.EntitySelector:
    cfg = selector.EntitySelectorConfig(domain=domain, multiple=multiple)
    if device_class:
        cfg = selector.EntitySelectorConfig(domain=domain, device_class=device_class, multiple=multiple)
    return selector.EntitySelector(cfg)


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_KITCHEN_POWER): _ent("sensor", "power"),
        vol.Required(CONF_COOKING_WATTS): _num(100, 5000, 50, "W"),
        vol.Optional(CONF_BATH_HUMIDITY): _ent("sensor", "humidity", multiple=True),
        vol.Required(CONF_BATH_LIMIT): _num(40, 100, 1, "%"),
        vol.Optional(CONF_ROOM_HUMIDITY): _ent("sensor", "humidity"),
        vol.Required(CONF_ROOM_LIMIT): _num(40, 100, 1, "%"),
        vol.Optional(CONF_CO2): _ent("sensor", "carbon_dioxide"),
        vol.Required(CONF_CO2_LIMIT): _num(400, 3000, 50, "ppm"),
        vol.Optional(CONF_INDOOR_TEMP): _ent("sensor", "temperature"),
        vol.Optional(CONF_PRESENCE): _ent(["binary_sensor", "person", "group", "input_boolean", "zone"]),
        vol.Optional(CONF_VACATION): _ent(["input_boolean", "binary_sensor", "switch"]),
        vol.Optional(CONF_WEEKLY_PLAN): _ent("schedule"),
        vol.Required(CONF_HEATING_MONTHS): selector.SelectSelector(
            selector.SelectSelectorConfig(options=MONTHS, multiple=True, mode=selector.SelectSelectorMode.LIST)),
        vol.Required(CONF_COOLING_MONTHS): selector.SelectSelector(
            selector.SelectSelectorConfig(options=MONTHS, multiple=True, mode=selector.SelectSelectorMode.LIST)),
        vol.Required(CONF_NIGHT_START): _num(0, 23, 1, "h"),
        vol.Required(CONF_NIGHT_END): _num(0, 23, 1, "h"),
    }
)


class VitoventConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            prefix = user_input[CONF_PREFIX].strip().rstrip("/")
            await self.async_set_unique_id(prefix)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Vitovent 300-W", data={CONF_PREFIX: prefix}, options=dict(DEFAULTS))
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_PREFIX, default=DEFAULT_PREFIX): str}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return VitoventOptionsFlow()


class VitoventOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # numbers from the UI arrive as float – store whole numbers as int
            data = {k: (int(v) if isinstance(v, float) and v.is_integer() else v) for k, v in user_input.items()}
            return self.async_create_entry(data=data)
        current = {**DEFAULTS, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, current))
