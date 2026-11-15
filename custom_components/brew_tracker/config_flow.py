"""Setup and options screens: which notify services to alert, and at what time of day."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (SelectSelector, SelectSelectorConfig, SelectSelectorMode, TimeSelector)

from .const import CONF_NOTIFY, CONF_NOTIFY_TIME, DEFAULT_NOTIFY_TIME, DOMAIN

_SKIP = {"notify", "send_message", "persistent_notification"}


def _schema(hass, notify: list[str], when: str) -> vol.Schema:
    available = sorted(s for s in hass.services.async_services().get("notify", {}) if s not in _SKIP)
    options = sorted(set(available) | set(notify))
    return vol.Schema({
        vol.Optional(CONF_NOTIFY, default=notify): SelectSelector(SelectSelectorConfig(
            options=options, multiple=True, custom_value=True, mode=SelectSelectorMode.DROPDOWN)),
        vol.Required(CONF_NOTIFY_TIME, default=when): TimeSelector(),
    })


class BrewTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Brew Tracker for Pinter", data={
                CONF_NOTIFY: user_input.get(CONF_NOTIFY, []), CONF_NOTIFY_TIME: user_input[CONF_NOTIFY_TIME]})
        return self.async_show_form(step_id="user", data_schema=_schema(self.hass, [], DEFAULT_NOTIFY_TIME))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BrewTrackerOptionsFlow()


class BrewTrackerOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={
                CONF_NOTIFY: user_input.get(CONF_NOTIFY, []), CONF_NOTIFY_TIME: user_input[CONF_NOTIFY_TIME]})
        entry = self.config_entry
        notify = list(entry.options.get(CONF_NOTIFY, entry.data.get(CONF_NOTIFY, [])))
        when = entry.options.get(CONF_NOTIFY_TIME, entry.data.get(CONF_NOTIFY_TIME, DEFAULT_NOTIFY_TIME))
        return self.async_show_form(step_id="init", data_schema=_schema(self.hass, notify, when))
