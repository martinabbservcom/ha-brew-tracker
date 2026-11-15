"""End to end: set the integration up in a test Home Assistant and use it through its services."""
from dataclasses import replace
from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.brew_tracker.const import DOMAIN


async def setup(hass: HomeAssistant):
    calls = async_mock_service(hass, "notify", "test_phone")
    entry = MockConfigEntry(domain=DOMAIN, data={"notify_services": ["test_phone"], "notify_time": "09:00:00"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, calls


async def call(hass, service, data, **kw):
    return await hass.services.async_call(DOMAIN, service, data, blocking=True, **kw)


async def add_beers_and_pinters(hass):
    await call(hass, "save_beer", {"name": "London Pride", "abv": 4.7, "brew_min": 5, "brew_rec": 7, "cond_min": 3, "cond_rec": 5, "crash": 3})
    await call(hass, "save_beer", {"name": "Elvis Juice", "abv": 6.5, "brew_min": 7, "brew_rec": 9, "cond_min": 3, "cond_rec": 5, "crash": 3, "hopper": True})
    await call(hass, "add_pinter", {"name": "Bluey"})
    await call(hass, "add_pinter", {"name": "The Black One"})
    await hass.async_block_till_done()


async def test_start_a_brew_from_the_inventory(hass: HomeAssistant):
    await setup(hass)
    await add_beers_and_pinters(hass)
    assert hass.states.get("sensor.bluey").state == "Empty"
    result = await call(hass, "start_brew", {"pinter": "Bluey", "beer": "London Pride", "brew_days": 10}, return_response=True)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.bluey")
    assert state.state == "Brewing"
    assert state.attributes["beer"] == "London Pride" and state.attributes["abv"] == 4.7
    assert state.attributes["step_days"] == 10 and state.attributes["next_step"] == "Cold Crashing"
    assert [r["step"] for r in state.attributes["plan"]] == ["Brewing", "Cold Crashing", "Conditioning"]
    assert result["state"] == "Free"
    inventory = hass.states.get("sensor.brew_tracker_beer_inventory")
    assert inventory.state == "2" and inventory.attributes["empty_pinters"] == ["The Black One"]


async def test_only_inventory_beers_and_empty_pinters(hass: HomeAssistant):
    await setup(hass)
    await add_beers_and_pinters(hass)
    with pytest.raises(ServiceValidationError, match="not in the beer inventory"):
        await call(hass, "start_brew", {"pinter": "Bluey", "beer": "Some Other Beer"})
    await call(hass, "start_brew", {"pinter": "Bluey", "beer": "London Pride"})
    with pytest.raises(ServiceValidationError, match="not empty"):
        await call(hass, "start_brew", {"pinter": "Bluey", "beer": "Elvis Juice"})
    with pytest.raises(ServiceValidationError, match="has a brew in it"):
        await call(hass, "remove_pinter", {"pinter": "Bluey"})
    with pytest.raises(ServiceValidationError, match="already in the inventory"):
        await call(hass, "add_pinter", {"name": "bluey"})


async def test_fridge_clash_and_handover(hass: HomeAssistant):
    await setup(hass)
    await add_beers_and_pinters(hass)
    await call(hass, "start_brew", {"pinter": "Bluey", "beer": "London Pride", "brew_days": 10, "crash_days": 3})
    await call(hass, "start_brew", {"pinter": "The Black One", "beer": "Elvis Juice", "brew_days": 13, "crash_days": 3})
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.brew_tracker_cold_crash_fridge_clash").state == "off"      # the same-day swap is fine
    assert hass.states.get("sensor.brew_tracker_cold_crash_fridge").attributes["handovers"]
    check = await call(hass, "check_brew", {"beer": "London Pride", "brew_days": 10, "crash_days": 3}, return_response=True)
    assert check["state"] == "Clash"
    await call(hass, "empty", {"pinter": "The Black One"})
    await call(hass, "start_brew", {"pinter": "The Black One", "beer": "Elvis Juice", "brew_days": 10, "crash_days": 4})
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.brew_tracker_cold_crash_fridge_clash").state == "on"
    assert hass.states.get("sensor.brew_tracker_cold_crash_fridge").state == "Clash"


async def test_move_on_go_back_and_empty(hass: HomeAssistant):
    await setup(hass)
    await add_beers_and_pinters(hass)
    await call(hass, "start_brew", {"pinter": "Bluey", "beer": "London Pride"})
    await call(hass, "move_on", {"pinter": "Bluey", "from_step": "Conditioning"})            # wrong step: does nothing
    assert hass.states.get("sensor.bluey").state == "Brewing"
    await call(hass, "move_on", {"pinter": "Bluey"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bluey").state == "Cold Crashing"
    assert hass.states.get("sensor.brew_tracker_cold_crash_fridge").state == "In use"
    await call(hass, "go_back", {"pinter": "Bluey"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bluey").state == "Brewing"
    with pytest.raises(ServiceValidationError, match="no earlier step"):
        await call(hass, "go_back", {"pinter": "Bluey"})
    await call(hass, "empty", {"pinter": "Bluey"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bluey").state == "Empty"


async def test_notification_is_sent_once_when_due_and_the_button_moves_it_on(hass: HomeAssistant):
    entry, calls = await setup(hass)
    await add_beers_and_pinters(hass)
    await call(hass, "start_brew", {"pinter": "Bluey", "beer": "London Pride", "brew_days": 10})
    manager = entry.runtime_data
    pid = manager.pinter_id("Bluey")
    manager.brews[pid] = replace(manager.brews[pid], step_start=dt_util.now() - timedelta(days=11))
    await manager.async_check_due()
    await hass.async_block_till_done()
    assert len(calls) == 1
    sent = calls[0].data
    assert sent["message"] == "Bluey: brewing London Pride. Move it on to Cold Crashing. Put it in the fridge with its dock attached."
    assert sent["title"] == "Bluey: time to move on"
    action = sent["data"]["actions"][0]
    assert action["title"] == "Done - I moved it"
    await manager.async_check_due()
    assert len(calls) == 1                                                                # only once
    hass.bus.async_fire("mobile_app_notification_action", {"action": action["action"]})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bluey").state == "Cold Crashing"
    hass.bus.async_fire("mobile_app_notification_action", {"action": action["action"]})   # a second tap on the old notification
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bluey").state == "Cold Crashing"


async def test_finished_conditioning_becomes_ready_to_drink(hass: HomeAssistant):
    entry, calls = await setup(hass)
    await add_beers_and_pinters(hass)
    await call(hass, "start_brew", {"pinter": "The Black One", "beer": "Elvis Juice", "cond_days": 5})
    manager = entry.runtime_data
    pid = manager.pinter_id("The Black One")
    manager.brews[pid] = replace(manager.brews[pid], step="Conditioning", step_start=dt_util.now() - timedelta(days=6))
    await manager.async_check_due()
    await hass.async_block_till_done()
    assert calls[-1].data["message"] == "The Black One: Elvis Juice (6.5%) has finished conditioning. It is ready to drink!"
    assert "actions" not in calls[-1].data["data"]
    assert hass.states.get("sensor.the_black_one").state == "Ready to drink"


async def test_data_survives_a_restart(hass: HomeAssistant):
    entry, _ = await setup(hass)
    await add_beers_and_pinters(hass)
    await call(hass, "start_brew", {"pinter": "Bluey", "beer": "London Pride"})
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bluey").state == "Brewing"
    assert hass.states.get("sensor.brew_tracker_beer_inventory").state == "2"


async def test_removed_pinter_disappears(hass: HomeAssistant):
    await setup(hass)
    await add_beers_and_pinters(hass)
    await call(hass, "remove_pinter", {"pinter": "The Black One"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.the_black_one") is None
