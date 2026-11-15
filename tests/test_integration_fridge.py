"""Home Assistant level checks of the fridge setting (runs in CI, where the Home Assistant test tools work)."""
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.brew_tracker.const import DOMAIN


async def setup(hass: HomeAssistant, **settings):
    async_mock_service(hass, "notify", "test_phone")
    entry = MockConfigEntry(domain=DOMAIN, data={"notify_services": ["test_phone"], "notify_time": "09:00:00", **settings})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def call(hass, service, data, **kw):
    return await hass.services.async_call(DOMAIN, service, data, blocking=True, **kw)


async def basics(hass):
    await call(hass, "save_beer", {"name": "London Pride", "brew_rec": 7, "cond_rec": 5, "crash": 3})
    await call(hass, "add_pinter", {"name": "Bluey"})
    await call(hass, "add_pinter", {"name": "Red One"})


async def test_with_no_fridge_cold_crashing_is_skipped(hass: HomeAssistant):
    await setup(hass, fridge_capacity=0)
    await basics(hass)
    result = await call(hass, "start_brew", {"pinter": "Bluey", "beer": "London Pride", "crash_days": 3}, return_response=True)
    await hass.async_block_till_done()
    assert result["state"] == "No fridge"
    assert [r["step"] for r in hass.states.get("sensor.bluey").attributes["plan"]] == ["Brewing", "Conditioning"]
    assert hass.states.get("sensor.brew_tracker_cold_crash_fridge").state == "No fridge"
    assert hass.states.get("binary_sensor.brew_tracker_cold_crash_fridge_clash").state == "off"


async def test_room_for_two_pinters(hass: HomeAssistant):
    await setup(hass, fridge_capacity=2)
    await basics(hass)
    await call(hass, "start_brew", {"pinter": "Bluey", "beer": "London Pride", "brew_days": 10})
    await call(hass, "start_brew", {"pinter": "Red One", "beer": "London Pride", "brew_days": 10})
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.brew_tracker_cold_crash_fridge_clash").state == "off"
    assert hass.states.get("sensor.brew_tracker_cold_crash_fridge").attributes["capacity"] == 2


async def test_one_fridge_is_the_default(hass: HomeAssistant):
    await setup(hass)
    await basics(hass)
    await call(hass, "start_brew", {"pinter": "Bluey", "beer": "London Pride", "brew_days": 10})
    await call(hass, "start_brew", {"pinter": "Red One", "beer": "London Pride", "brew_days": 10})
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.brew_tracker_cold_crash_fridge_clash").state == "on"
