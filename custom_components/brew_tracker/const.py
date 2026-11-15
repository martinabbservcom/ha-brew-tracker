"""Constants for Brew Tracker for Pinter."""
DOMAIN = "brew_tracker"

CONF_NOTIFY = "notify_services"      # names under the notify domain, for example "mobile_app_my_phone"
CONF_NOTIFY_TIME = "notify_time"     # time of day for the move-on notification, "09:00:00"
DEFAULT_NOTIFY_TIME = "09:00:00"

STORAGE_VERSION = 1

SIGNAL_UPDATED = f"{DOMAIN}_updated"
SIGNAL_NEW_PINTER = f"{DOMAIN}_new_pinter"

EVENT_MOBILE_ACTION = "mobile_app_notification_action"
ACTION_PREFIX = "BREW_TRACKER_NEXT"   # "BREW_TRACKER_NEXT|<pinter id>|<step it was on>"

EMPTY = "Empty"
