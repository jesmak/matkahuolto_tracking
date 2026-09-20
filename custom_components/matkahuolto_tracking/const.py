"""Constants for the Matkahuolto package tracking integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "matkahuolto_tracking"

ATTRIBUTION: Final = "Data provided by Oy Matkahuolto Ab"

API_BASE_URL: Final = "https://wwwservice.matkahuolto.fi"
PATH_USER: Final = "/user"
PATH_RECEIVED_SHIPMENTS: Final = "/history/parcel/received"
PATH_REFRESH_TOKEN: Final = "/user/token/refresh"
# The web service is made for matkahuolto.fi, so requests carry a browser's user agent.
USER_AGENT: Final = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/106.0.5249.62 Safari/537.36"
)

# Languages of the package event descriptions.
LANGUAGES: Final = ["fi", "en"]

# Config entry data. The keys are those of earlier versions, so existing entries keep working.
CONF_USERNAME: Final = "username"
CONF_ACCESS_TOKEN: Final = "access_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_LANGUAGE: Final = "language"
CONF_PRIORITIZE_UNDELIVERED: Final = "prioritize_undelivered"
CONF_MAX_SHIPMENTS: Final = "max_shipments"
CONF_STALE_SHIPMENT_DAY_LIMIT: Final = "stale_shipment_day_limit"
CONF_COMPLETED_SHIPMENT_DAYS_SHOWN: Final = "completed_shipment_day_shown"
CONF_INCLUDE_PICKUP_DETAILS: Final = "include_pickup_details"

DEFAULT_PRIORITIZE_UNDELIVERED: Final = True
# The pickup point and its code are left out unless asked for: the code collects the package.
DEFAULT_INCLUDE_PICKUP_DETAILS: Final = False
DEFAULT_MAX_SHIPMENTS: Final = 5
DEFAULT_STALE_SHIPMENT_DAY_LIMIT: Final = 15
DEFAULT_COMPLETED_SHIPMENT_DAYS_SHOWN: Final = 3

UPDATE_INTERVAL: Final = timedelta(minutes=10)

# Matkahuolto's event times have no time zone: they are Finnish time.
TIME_ZONE: Final = "Europe/Helsinki"
