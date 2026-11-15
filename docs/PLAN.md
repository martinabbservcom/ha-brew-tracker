# Plan

Goal: a Home Assistant custom integration, installed through HACS, that anyone can set up and use straight away.
Proven first as the replacement for a working YAML setup (6 Pinter slots, beer inventory, notifications, Cold Crash fridge
check) that runs on the author's own Home Assistant.

## Decisions

- Custom integration (`custom_components/brew_tracker`), HACS custom repository first, default HACS later if it takes off.
- Any number of Pinters. Beers (inventory) and brews are stored in Home Assistant's own storage (`homeassistant.helpers.storage.Store`),
  no files or folders for the user to set up.
- Notifications go to the notify services the user picks in the config flow (any number), with a "Done, I moved it" action
  button on mobile app notifications.
- A custom Lovelace card, bundled with the integration and registered automatically, shows the brewing Pinters, the
  start-a-brew form and the beer inventory. It uses no other custom cards.
- MIT licence. Donations by a PayPal.Me link (README badge and `.github/FUNDING.yml`). Unofficial: no Pinter branding or copied content.

## Data model

- Pinter: id, name.
- Beer (inventory): name, ABV, brewing days minimum and recommended, conditioning days minimum and recommended,
  Cold Crashing days, uses a hopper.
- Brew (one per non-empty Pinter): beer name, ABV, hopper, days per step, current step (Brewing, Cold Crashing,
  Conditioning, Ready to drink), when the step started, the step it came from and when that started (for Go back),
  notified flag.

Steps and dates follow the rules in the author's YAML version: a step's days count from when it started; Cold Crashing 0 skips it;
Conditioning ending moves to Ready to drink by itself; fridge clash means two Cold Crash windows overlap (a same-day swap is fine).

## Pieces

1. `store.py`: load and save Pinters, beers, brews; migrations.
2. `scheduler.py`: for each brew, schedule the move-on notification at the chosen time of day on the due date
   (`async_track_point_in_time`), rebuild on restart and on any change.
3. `entities`: a sensor per Pinter (state = step; attributes = beer, ABV, plan, due date, days left), a fridge sensor and a
   fridge-clash binary sensor, a calendar of the move-on dates.
4. `services.yaml`: start_brew, move_on, go_back, empty, add_pinter, remove_pinter, save_beer, delete_beer, send_test_notification.
5. `config_flow.py`: notify services, notification time, default Cold Crash days; options flow to change them.
6. `notify.py`: build the message and send to the chosen services; handle the notification action event.
7. `www/brew-tracker-card.js`: the bundled card.
8. Translations (English first), tests with `pytest-homeassistant-custom-component`, CI (hassfest, HACS validation, tests).

## Milestones

1. Core: store, entities, services, scheduler, with tests.
2. Notifications, action button, fridge check.
3. The card.
4. Move the author's own setup onto it and run a full brew cycle.
5. Release 0.1.0 (still a HACS custom repository), then make the repository public and announce.

## Rules

- Never commit secrets, personal entity names or household details.
- Test only with data the tests create; never reset or overwrite anything a user entered.
