"""Constants for Brew Tracker for Pinter."""
DOMAIN = "brew_tracker"

CONF_NOTIFY = "notify_services"      # names under the notify domain, for example "mobile_app_my_phone"
CONF_NOTIFY_TIME = "notify_time"     # time of day for the move-on notification, "09:00:00"
DEFAULT_NOTIFY_TIME = "09:00:00"

CONF_FRIDGE_CAPACITY = "fridge_capacity"          # how many Pinters can be Cold Crashed at once (0 = no fridge)
CONF_CONDITIONING_IN_FRIDGE = "conditioning_in_fridge"   # Conditioning also takes fridge room
DEFAULT_FRIDGE_CAPACITY = 1

VERSION = "0.1.0"          # keep in step with manifest.json
CARD_URL = f"/{DOMAIN}/brew-tracker-card.js"

STORAGE_VERSION = 1

SIGNAL_UPDATED = f"{DOMAIN}_updated"
SIGNAL_NEW_PINTER = f"{DOMAIN}_new_pinter"

EVENT_MOBILE_ACTION = "mobile_app_notification_action"
ACTION_PREFIX = "BREW_TRACKER_NEXT"   # "BREW_TRACKER_NEXT|<pinter id>|<step it was on>"

EMPTY = "Empty"
