"""A whole brew cycle for two Pinters, with the clock moved forward day by day.

Uses the real brews this was built for: Bluey (London Pride, brew 10 / Cold Crash 3 / condition 5, started Sun 15 Nov 15:03) and
The Black One (Elvis Juice with a hopper, brew 13 / 3 / 5, started the same day 15:37). The notification time is 09:00.
"""
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, async_mock_service

from custom_components.brew_tracker.const import DOMAIN


async def call(hass, service, data, **kw):
    return await hass.services.async_call(DOMAIN, service, data, blocking=True, **kw)


async def at(hass: HomeAssistant, freezer, when: str) -> None:
    """Move the clock to `when` (London time, which is UTC in winter) and let the minute check run."""
    freezer.move_to(when)
    async_fire_time_changed(hass, dt_util.parse_datetime(when))
    await hass.async_block_till_done()


def sent(calls):
    return [c.data["message"] for c in calls]


async def test_two_pinters_through_a_whole_brew_with_a_late_move(hass: HomeAssistant, freezer):
    await hass.config.async_set_time_zone("Europe/London")
    freezer.move_to("2026-11-15 15:03:37+00:00")
    calls = async_mock_service(hass, "notify", "phone")
    entry = MockConfigEntry(domain=DOMAIN, data={"notify_services": ["phone"], "notify_time": "09:00:00", "fridge_capacity": 1})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await call(hass, "save_beer", {"name": "London Pride", "abv": 4.7, "brew_min": 5, "brew_rec": 7, "cond_min": 3, "cond_rec": 5, "crash": 3})
    await call(hass, "save_beer", {"name": "Elvis Juice", "abv": 6.5, "brew_min": 7, "brew_rec": 9, "cond_min": 3, "cond_rec": 5, "crash": 3, "hopper": True})
    await call(hass, "add_pinter", {"name": "Bluey"})
    await call(hass, "add_pinter", {"name": "The Black One"})
    await call(hass, "start_brew", {"pinter": "Bluey", "beer": "London Pride", "brew_days": 10, "crash_days": 3, "cond_days": 5})
    freezer.move_to("2026-11-15 15:37:24+00:00")
    await call(hass, "start_brew", {"pinter": "The Black One", "beer": "Elvis Juice", "brew_days": 13, "crash_days": 3, "cond_days": 5})
    await hass.async_block_till_done()

    bluey, black = (lambda n: hass.states.get(n))("sensor.bluey"), hass.states.get("sensor.the_black_one")
    assert bluey.attributes["due"] == "2026-11-25" and black.attributes["due"] == "2026-11-28"
    assert black.attributes["hopper_note"] == "The hopper goes in when the dock comes off."
    assert hass.states.get("binary_sensor.brew_tracker_cold_crash_fridge_clash").state == "off"

    # ---- days pass with nothing due: no notifications
    await at(hass, freezer, "2026-11-20 09:30:00+00:00")
    await at(hass, freezer, "2026-11-25 08:59:00+00:00")
    assert calls == []

    # ---- Wed 25 Nov 09:00: Bluey is due, notified once
    await at(hass, freezer, "2026-11-25 09:01:00+00:00")
    assert sent(calls) == ["Bluey: brewing London Pride. Move it on to Cold Crashing. Put it in the fridge with its dock attached."]
    assert hass.states.get("sensor.bluey").attributes["overdue"] is True
    await at(hass, freezer, "2026-11-25 18:00:00+00:00")
    assert len(calls) == 1                                                    # only once

    # ---- Bluey is moved on from the phone at 18:05 (the Done button)
    action = calls[0].data["data"]["actions"][0]["action"]
    freezer.move_to("2026-11-25 18:05:00+00:00")
    hass.bus.async_fire("mobile_app_notification_action", {"action": action})
    await hass.async_block_till_done()
    bluey = hass.states.get("sensor.bluey")
    assert bluey.state == "Cold Crashing" and bluey.attributes["due"] == "2026-11-28"
    assert hass.states.get("sensor.brew_tracker_cold_crash_fridge").state == "In use"

    # ---- Sat 28 Nov 09:00: both are due. Bluey leaves the fridge, The Black One wants in (Bluey has not been moved yet)
    await at(hass, freezer, "2026-11-28 09:01:00+00:00")
    messages = sent(calls)[1:]
    assert len(messages) == 2
    bluey_msg = next(m for m in messages if m.startswith("Bluey"))
    black_msg = next(m for m in messages if m.startswith("The Black One"))
    assert bluey_msg == ("Bluey: cold crashing London Pride. Move it on to Conditioning. "
                         "Take the dock off and put it back in the fridge in its tapping position.")
    assert black_msg == ("The Black One: brewing Elvis Juice. Move it on to Cold Crashing. Put it in the fridge with its dock attached. "
                         "Heads up: the cold crash fridge is in use by Bluey (London Pride) until Sat 28 Nov.")

    # ---- the user moves Bluey out first, then The Black One in (late: 28 Nov 10:00 and 10:05)
    freezer.move_to("2026-11-28 10:00:00+00:00")
    await call(hass, "move_on", {"pinter": "Bluey"})
    freezer.move_to("2026-11-28 10:05:00+00:00")
    await call(hass, "move_on", {"pinter": "The Black One"})
    await hass.async_block_till_done()
    bluey, black = hass.states.get("sensor.bluey"), hass.states.get("sensor.the_black_one")
    assert (bluey.state, bluey.attributes["due"]) == ("Conditioning", "2026-12-03")
    assert (black.state, black.attributes["due"]) == ("Cold Crashing", "2026-12-01")
    assert hass.states.get("binary_sensor.brew_tracker_cold_crash_fridge_clash").state == "off"

    # ---- Tue 1 Dec: The Black One comes out of the fridge; the dock comes off and the hopper goes in
    await at(hass, freezer, "2026-12-01 09:01:00+00:00")
    assert sent(calls)[-1] == ("The Black One: cold crashing Elvis Juice. Move it on to Conditioning. "
                               "Take the dock off, put the hopper in, and put it back in the fridge in its tapping position.")

    # ---- Thu 3 Dec: Bluey has finished conditioning, so it is ready to drink with no action needed
    await at(hass, freezer, "2026-12-03 09:01:00+00:00")
    assert sent(calls)[-1] == "Bluey: London Pride (4.7%) has finished conditioning. It is ready to drink!"
    assert "actions" not in calls[-1].data["data"]
    assert hass.states.get("sensor.bluey").state == "Ready to drink"

    # ---- The Black One is moved to Conditioning late, 1 Dec 12:00, so its dates move back with it
    freezer.move_to("2026-12-01 12:00:00+00:00")
    await call(hass, "move_on", {"pinter": "The Black One"})
    await hass.async_block_till_done()
    black = hass.states.get("sensor.the_black_one")
    assert (black.state, black.attributes["due"], black.attributes["ready_on"]) == ("Conditioning", "2026-12-06", "2026-12-06")
    await at(hass, freezer, "2026-12-06 09:01:00+00:00")
    assert sent(calls)[-1] == "The Black One: Elvis Juice (6.5%) has finished conditioning. It is ready to drink!"
    assert hass.states.get("sensor.the_black_one").state == "Ready to drink"

    # ---- finished: empty both, and nothing else was sent
    await call(hass, "empty", {"pinter": "Bluey"})
    await call(hass, "empty", {"pinter": "The Black One"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bluey").state == hass.states.get("sensor.the_black_one").state == "Empty"
    assert hass.states.get("sensor.brew_tracker_cold_crash_fridge").state == "Free"
    assert len(calls) == 6


async def test_go_back_after_a_wrong_tap_and_no_repeat_notification(hass: HomeAssistant, freezer):
    await hass.config.async_set_time_zone("Europe/London")
    freezer.move_to("2026-11-15 15:03:37+00:00")
    calls = async_mock_service(hass, "notify", "phone")
    entry = MockConfigEntry(domain=DOMAIN, data={"notify_services": ["phone"], "notify_time": "09:00:00"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await call(hass, "save_beer", {"name": "London Pride", "brew_rec": 7, "cond_rec": 5})
    await call(hass, "add_pinter", {"name": "Bluey"})
    await call(hass, "start_brew", {"pinter": "Bluey", "beer": "London Pride", "brew_days": 10})
    await at(hass, freezer, "2026-11-25 09:01:00+00:00")
    assert len(calls) == 1
    await call(hass, "move_on", {"pinter": "Bluey"})                           # moved on...
    await call(hass, "go_back", {"pinter": "Bluey"})                           # ...then a wrong tap is undone
    await hass.async_block_till_done()
    bluey = hass.states.get("sensor.bluey")
    assert bluey.state == "Brewing" and bluey.attributes["started"].startswith("2026-11-15T15:03:37")
    await at(hass, freezer, "2026-11-25 09:05:00+00:00")
    assert len(calls) == 1                                                    # already notified, so no repeat
