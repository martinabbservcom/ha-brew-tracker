"""Setup and options screens: which notify services to alert, and at what time of day."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (BooleanSelector, NumberSelector, NumberSelectorConfig, NumberSelectorMode,
                                            SelectSelector, SelectSelectorConfig, SelectSelectorMode, TimeSelector)

from .const import (CONF_CONDITIONING_IN_FRIDGE, CONF_FRIDGE_CAPACITY, CONF_NOTIFY, CONF_NOTIFY_TIME,
                    DEFAULT_FRIDGE_CAPACITY, DEFAULT_NOTIFY_TIME, DOMAIN)

_SKIP = {"notify", "send_message", "persistent_notification"}


def _schema(hass, notify: list[str], when: str, fridges: int = DEFAULT_FRIDGE_CAPACITY, cond: bool = False) -> vol.Schema:
    available = sorted(s for s in hass.services.async_services().get("notify", {}) if s not in _SKIP)
    options = sorted(set(available) | set(notify))
    return vol.Schema({
        vol.Optional(CONF_NOTIFY, default=notify): SelectSelector(SelectSelectorConfig(
            options=options, multiple=True, custom_value=True, mode=SelectSelectorMode.DROPDOWN)),
        vol.Required(CONF_NOTIFY_TIME, default=when): TimeSelector(),
        vol.Required(CONF_FRIDGE_CAPACITY, default=fridges): NumberSelector(NumberSelectorConfig(
            min=0, max=6, step=1, mode=NumberSelectorMode.BOX)),
        vol.Required(CONF_CONDITIONING_IN_FRIDGE, default=cond): BooleanSelector(),
    })


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_NOTIFY: user_input.get(CONF_NOTIFY, []),
        CONF_NOTIFY_TIME: user_input[CONF_NOTIFY_TIME],
        CONF_FRIDGE_CAPACITY: int(user_input.get(CONF_FRIDGE_CAPACITY, DEFAULT_FRIDGE_CAPACITY)),
        CONF_CONDITIONING_IN_FRIDGE: bool(user_input.get(CONF_CONDITIONING_IN_FRIDGE, False)),
    }


class BrewTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Brew Tracker for Pinter", data=_clean(user_input))
        return self.async_show_form(step_id="user", data_schema=_schema(self.hass, [], DEFAULT_NOTIFY_TIME))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BrewTrackerOptionsFlow()


class BrewTrackerOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_clean(user_input))
        entry = self.config_entry
        notify = list(entry.options.get(CONF_NOTIFY, entry.data.get(CONF_NOTIFY, [])))
        when = entry.options.get(CONF_NOTIFY_TIME, entry.data.get(CONF_NOTIFY_TIME, DEFAULT_NOTIFY_TIME))
        fridges = int(entry.options.get(CONF_FRIDGE_CAPACITY, entry.data.get(CONF_FRIDGE_CAPACITY, DEFAULT_FRIDGE_CAPACITY)))
        cond = bool(entry.options.get(CONF_CONDITIONING_IN_FRIDGE, entry.data.get(CONF_CONDITIONING_IN_FRIDGE, False)))
        return self.async_show_form(step_id="init", data_schema=_schema(self.hass, notify, when, fridges, cond))
