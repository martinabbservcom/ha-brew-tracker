"""The fridge room is a setting: none, one, several, and whether Conditioning also takes room."""
from datetime import date, datetime, timezone

from custom_components.brew_tracker import logic as L

UTC = timezone.utc
BEER = L.Beer("Test beer", brew_rec=7, cond_rec=5, crash=3)


def dt(day, month=11):
    return datetime(2026, month, day, 15, 3, 37, tzinfo=UTC)


def brew(start_day, brew_days=10, crash=3, cond=5):
    return L.start_brew(BEER, dt(start_day), brew_days=brew_days, crash_days=crash, cond_days=cond)


def windows(*named, conditioning=False):
    return L.fridge_windows({str(i): pair for i, pair in enumerate(named)}, conditioning)


def test_no_fridge_means_cold_crashing_is_not_possible():
    w = windows(("A", brew(15)))
    assert L.fridge_check(w, capacity=0)["state"] == "No fridge"
    state, text = L.check_new_brew(w, date(2026, 11, 15), 10, 3, capacity=0)
    assert state == "No fridge" and "skips it" in text


def test_room_for_two_allows_two_but_not_three():
    a, b, c = brew(15), brew(15), brew(16)            # all Cold Crashing around 25-29 Nov
    two = windows(("A", a), ("B", b))
    assert L.fridge_check(two, capacity=1)["state"] == "Clash"
    assert L.fridge_check(two, capacity=2)["state"] == "Free"
    three = windows(("A", a), ("B", b), ("C", c))
    check = L.fridge_check(three, capacity=2)
    assert check["state"] == "Clash"
    assert "only room for 2" in check["conflicts"][0]["text"] and "A (Test beer)" in check["conflicts"][0]["text"]


def test_new_brew_preview_with_room_for_two():
    existing = windows(("A", brew(15)))
    assert L.check_new_brew(existing, date(2026, 11, 15), 10, 3, capacity=1)[0] == "Clash"
    assert L.check_new_brew(existing, date(2026, 11, 15), 10, 3, capacity=2)[0] == "Free"
    both = windows(("A", brew(15)), ("B", brew(15)))
    state, text = L.check_new_brew(both, date(2026, 11, 15), 10, 3, capacity=2)
    assert state == "Clash" and "FRIDGE FULL" in text and "2 places" in text


def test_conditioning_takes_fridge_room_when_the_setting_is_on():
    a = brew(15)                                        # Cold Crash 25-28 Nov, Conditioning 28 Nov - 3 Dec
    b = brew(15, brew_days=14)                          # Cold Crash 29 Nov - 2 Dec
    pair = lambda cond: windows(("A", a), ("B", b), conditioning=cond)
    assert L.fridge_check(pair(False), capacity=1)["state"] == "Free"          # the crashes do not overlap
    assert L.fridge_check(pair(True), capacity=1)["state"] == "Clash"          # A is still conditioning in the fridge
    window = pair(True)[0]
    assert (window.start, window.end) == (date(2026, 11, 25), date(2026, 12, 3))


def test_conditioning_only_window_when_cold_crash_is_skipped():
    no_crash = brew(15, crash=0)
    assert windows(("A", no_crash)) == []
    w = windows(("A", no_crash), conditioning=True)
    assert [(x.start, x.end) for x in w] == [(date(2026, 11, 25), date(2026, 11, 30))]
    state, _ = L.check_new_brew([], date(2026, 11, 15), 10, 0, capacity=1, cond_days=5, conditioning_in_fridge=True)
    assert state == "Free"
    assert L.check_new_brew([], date(2026, 11, 15), 10, 0, capacity=1)[0] == "No Cold Crashing"


def test_a_pinter_already_conditioning_only_uses_room_for_the_rest_of_conditioning():
    from dataclasses import replace
    cond = replace(brew(15), step="Conditioning", step_start=dt(28))
    assert windows(("A", cond)) == []
    w = windows(("A", cond), conditioning=True)
    assert w[0].in_fridge and (w[0].start, w[0].end) == (date(2026, 11, 28), date(2026, 12, 3))
