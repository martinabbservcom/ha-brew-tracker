<img src="assets/logo.png" alt="Brew Tracker for Pinter logo" width="96" align="right">

# Brew Tracker for Pinter

> **Status: early release (0.0.x).** It runs a real household's brews, but expect rough edges. Please report problems in the issues.

A Home Assistant integration for keeping track of home brews in [Pinter](https://pinter.co.uk) brewing vessels:
which Pinter has which beer in it, what step it is on, which day and date to move it on, and a notification to your
phones when it is time.

**Unofficial.** This is a community project. It is not made by, affiliated with or endorsed by Pinter. "Pinter" is
their name; no Pinter logos, text or images are used here. The Pinter itself has no connection to Home Assistant, so
this tracks the dates and steps you give it, it does not read anything from the vessel.

## What it does

- Any number of Pinters, each with a name, and a beer inventory you fill in (ABV, minimum and recommended brewing and
  conditioning days, Cold Crashing days, whether it uses a hopper).
- Start a brew by picking a beer and an empty Pinter. The days fill in from the beer and can be adjusted.
- Steps: Brewing, then Cold Crashing (optional, in the fridge with the dock attached), then Conditioning (dock off, the
  hopper goes in if the beer has one, back in the fridge in its tapping position), then Ready to drink.
- Notifications to the phones or notify services you choose, on the day each move is due, saying which Pinter, which beer and
  the step to move it on to, with a "Done, I moved it" button.
- Fridge room is a setting, because everyone's setup is different: how many Pinters you can Cold Crash at once (0 means you
  have no fridge for it, so Cold Crashing is skipped), and whether Conditioning also takes room in the same fridge. You get a
  warning if the dates would need more room than you have.
- Go back (undo) a move, with a confirmation.
- A card that installs with the integration.

## Install

1. In HACS, open the menu (three dots), choose Custom repositories, add `https://github.com/martinabbservcom/ha-brew-tracker` with the category Integration, then install it.
2. Restart Home Assistant, then add the integration under Settings, Devices and services (search for Brew Tracker for Pinter).
3. Choose which notify services to use, the notification time and your fridge room. All of these can be changed later with the Configure button.
4. Add the card to a dashboard (see below).

## The dashboard card

The card is added for you when the integration loads. Add it to any dashboard (Edit dashboard, Add card, Manual):

```yaml
type: custom:brew-tracker-card
```

It has four tabs: Brewing (what to do next for each Pinter, Moved it on, Go back), Start brew, Pinters (add, remove, empty)
and Beers (the inventory). To open it on a particular tab, add `tab: brewing`, `tab: start`, `tab: pinters` or `tab: beers`.
If the card shows "custom element doesn't exist" after installing, refresh the browser page once.

## Support the project

It is free and open source. If it is useful to you, a donation is a welcome thank-you:

[![Donate with PayPal](https://img.shields.io/badge/Donate-PayPal-0070ba?logo=paypal&logoColor=white)](https://paypal.me/martin2099)

Donations are optional and do not buy extra features or priority support.

## Licence

MIT. See [LICENSE](LICENSE).

---

A project by [abbserv.com](https://abbserv.com).
