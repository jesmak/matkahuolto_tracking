"""Constants for the Matkahuolto package tracking integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "matkahuolto_tracking"

ATTRIBUTION: Final = "Data provided by Oy Matkahuolto Ab"

# The carrier's own page for a package, given with each package so that package-tracker-card can open it.
TRACKING_URL: Final = "https://www.matkahuolto.fi/seuranta?parcelNumber={number}"

API_BASE_URL: Final = "https://wwwservice.matkahuolto.fi"
PATH_USER: Final = "/user"
PATH_RECEIVED_SHIPMENTS: Final = "/history/parcel/received"
PATH_SENT_SHIPMENTS: Final = "/history/parcel/sent"
PATH_REFRESH_TOKEN: Final = "/user/token/refresh"
PATH_AUTH: Final = "/user/auth"
# The web service is made for matkahuolto.fi, so requests carry a browser's user agent.
USER_AGENT: Final = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.5249.62 Safari/537.36"
# The login is made the way the Matkahuolto Paketit app makes it: the website's login needs a reCAPTCHA,
# the app's doesn't. The endpoint turns away browser, curl and Python user agents with "400 Invalid
# request" before looking at the password, so the login carries the app's HTTP client and version.
# If logging in starts failing with that, bump the version to the app's current one
# (android/<versionName>.<versionCode>).
LOGIN_USER_AGENT: Final = "okhttp/4.12.0"
PAKETIT_CLIENT: Final = "android/1.64.1291"

# Languages of the package event descriptions.
LANGUAGES: Final = ["fi", "en"]

# Config entry data. The keys are those of earlier versions, so existing entries keep working.
# The email address the account was added with. The entities' ids are built from it, so it stays as it was.
CONF_USERNAME: Final = "username"
# The email address to log in with, when it has changed since the account was added.
CONF_EMAIL: Final = "email"
# The account's id in Matkahuolto's login service, which stays the same when its email changes. Saved at each login.
CONF_SUBJECT: Final = "subject"
# Kept so that a login can be made again when the refresh token stops working.
CONF_PASSWORD: Final = "password"
CONF_ACCESS_TOKEN: Final = "access_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_LANGUAGE: Final = "language"
CONF_PRIORITIZE_UNDELIVERED: Final = "prioritize_undelivered"
# The most received packages listed, and the most sent ones. 0 leaves that direction out altogether.
CONF_MAX_SHIPMENTS: Final = "max_shipments"
CONF_MAX_OUTGOING_SHIPMENTS: Final = "max_outgoing_shipments"
CONF_STALE_SHIPMENT_DAY_LIMIT: Final = "stale_shipment_day_limit"
CONF_COMPLETED_SHIPMENT_DAYS_SHOWN: Final = "completed_shipment_day_shown"
# Whether packages carry their pickup code. Before config entry version 2.3 (release 2.2.0) this was
# include_pickup_details, a switch that also held back the pickup point.
CONF_PICKUP_CODE: Final = "pickup_code"
CONF_INCLUDE_PICKUP_DETAILS: Final = "include_pickup_details"

DEFAULT_PRIORITIZE_UNDELIVERED: Final = True
PICKUP_CODE_NONE: Final = "none"
PICKUP_CODE_CODE: Final = "code"
PICKUP_CODE_OPTIONS: Final = [PICKUP_CODE_NONE, PICKUP_CODE_CODE]
# The code is left out unless asked for, since it collects the package.
DEFAULT_PICKUP_CODE: Final = PICKUP_CODE_NONE
DEFAULT_MAX_SHIPMENTS: Final = 5
DEFAULT_MAX_OUTGOING_SHIPMENTS: Final = 5
DEFAULT_STALE_SHIPMENT_DAY_LIMIT: Final = 15
DEFAULT_COMPLETED_SHIPMENT_DAYS_SHOWN: Final = 3

UPDATE_INTERVAL: Final = timedelta(minutes=10)

# Matkahuolto's event times have no time zone: they are Finnish time.
TIME_ZONE: Final = "Europe/Helsinki"
