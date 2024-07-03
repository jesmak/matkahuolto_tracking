import datetime
import logging
from datetime import (timedelta, datetime)
from typing import Any, Callable, Dict, Optional

from aiohttp import ClientError

from homeassistant import config_entries, core
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
)

from .session import MatkahuoltoSession
from .const import PATH_GET_SHIPMENTS, CONF_USERNAME, CONF_PASSWORD, CONF_LANGUAGE, CONF_MAX_SHIPMENTS, \
    CONF_STALE_SHIPMENT_DAY_LIMIT, CONF_COMPLETED_SHIPMENT_DAYS_SHOWN, DOMAIN, CONF_PRIORITIZE_UNDELIVERED

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=10)
ATTRIBUTION = "Data provided by Oy Matkahuolto Ab"

ATTR_PACKAGES = "packages"
ATTR_ORIGIN = "origin"
ATTR_ORIGIN_CITY = "origin_city"
ATTR_DESTINATION = "destination"
ATTR_DESTINATION_CITY = "destination_city"
ATTR_SHIPMENT_NUMBER = "shipment_number"
ATTR_SHIPMENT_DATE = "shipment_date"
ATTR_STATUS = "status"
ATTR_RAW_STATUS = "raw_status"
ATTR_LATEST_EVENT = "latest_event"
ATTR_LATEST_EVENT_COUNTRY = "latest_event_country"
ATTR_LATEST_EVENT_CITY = "latest_event_city"
ATTR_LATEST_EVENT_DATE = "latest_event_date"
ATTR_SOURCE = "source"


async def async_setup_platform(
        hass: HomeAssistant,
        config: ConfigType,
        async_add_entities: Callable,
        discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    session = MatkahuoltoSession(config[CONF_USERNAME], config[CONF_PASSWORD], config[CONF_LANGUAGE])
    await hass.async_add_executor_job(session.authenticate)
    async_add_entities(
        [MatkahuoltoSensor(
            session,
            config[CONF_USERNAME],
            config[CONF_LANGUAGE],
            config[CONF_PRIORITIZE_UNDELIVERED],
            config[CONF_MAX_SHIPMENTS],
            config[CONF_STALE_SHIPMENT_DAY_LIMIT],
            config[CONF_COMPLETED_SHIPMENT_DAYS_SHOWN]
        )],
        update_before_add=True
    )


async def async_setup_entry(hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry, async_add_entities):
    config = hass.data[DOMAIN][config_entry.entry_id]
    if config_entry.options:
        config.update(config_entry.options)
    session = MatkahuoltoSession(config[CONF_USERNAME], config[CONF_PASSWORD], config[CONF_LANGUAGE])
    await hass.async_add_executor_job(session.authenticate)
    async_add_entities(
        [MatkahuoltoSensor(
            session,
            config[CONF_USERNAME],
            config[CONF_LANGUAGE],
            config[CONF_PRIORITIZE_UNDELIVERED],
            config[CONF_MAX_SHIPMENTS],
            config[CONF_STALE_SHIPMENT_DAY_LIMIT],
            config[CONF_COMPLETED_SHIPMENT_DAYS_SHOWN]
        )],
        update_before_add=True
    )


class MatkahuoltoSensor(Entity):
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:package"
    _attr_native_unit_of_measurement = "packages"

    def __init__(
            self,
            session: MatkahuoltoSession,
            username: str,
            language: str,
            prioritize_undelivered: bool,
            max_shipments: int,
            stale_shipment_day_limit: int,
            completed_shipment_days_shown: int
    ):
        super().__init__()
        self._session = session
        self._username = username
        self._language = language
        self._prioritize_undelivered = prioritize_undelivered
        self._max_shipments = max_shipments
        self._stale_shipment_day_limit = stale_shipment_day_limit
        self._completed_shipment_days_shown = completed_shipment_days_shown
        self._state = None
        self._available = True
        self._attrs = {}

    @property
    def name(self) -> str:
        return f"matkahuolto_{self._username}"

    @property
    def unique_id(self) -> str:
        return f"matkahuolto_{self._username}"

    @property
    def available(self) -> bool:
        return self._available

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return self._attrs

    @property
    def state(self) -> Optional[str]:
        return self._state

    async def async_update(self):
        try:
            data = await self.hass.async_add_executor_job(self._session.call_api, PATH_GET_SHIPMENTS)

            latest_timestamp = None

            delivered_packages = []
            undelivered_packages = []

            timezone = datetime.now().astimezone().tzinfo
            now = datetime.now(timezone)

            for shipment in data["shipments"]:

                if "lastEvent" in shipment:
                    last_status_change = datetime.fromisoformat(str(shipment["lastEvent"]["time"])).replace(tzinfo=timezone)
                elif "deliveryTime" in shipment and shipment["deliveryTime"] is not None:
                    last_status_change = datetime.fromtimestamp(int(shipment["deliveryTime"] / 1000)).replace(tzinfo=timezone)
                else:
                    continue

                if latest_timestamp is None or last_status_change > latest_timestamp:
                    latest_timestamp = last_status_change

                status = map_raw_status(int(shipment["shipmentStatus"]))
                delta = now - last_status_change

                if status != 0 and delta.days <= self._stale_shipment_day_limit:
                    add_package(undelivered_packages, shipment, status)
                elif status == 0 and delta.days <= self._completed_shipment_days_shown:
                    add_package(delivered_packages, shipment, status)

            delivered_packages.sort(key=lambda x: x[ATTR_LATEST_EVENT_DATE], reverse=True)
            undelivered_packages.sort(key=lambda x: x[ATTR_LATEST_EVENT_DATE], reverse=True)

            package_data = undelivered_packages + delivered_packages

            if not self._prioritize_undelivered:
                package_data.sort(key=lambda x: x[ATTR_LATEST_EVENT_DATE], reverse=True)

            self._attrs[ATTR_PACKAGES] = package_data[0:min(len(package_data), self._max_shipments)]
            self._available = True
            self._state = latest_timestamp

        except ClientError:
            self._available = False


def add_package(package_data: list, shipment: any, status: int):
    package_data.append(
        {
            ATTR_ORIGIN: shipment["senderName"],
            ATTR_ORIGIN_CITY: shipment["senderCity"],
            ATTR_DESTINATION: shipment["destinationPlaceName"],
            ATTR_DESTINATION_CITY: shipment["receiverCity"],
            ATTR_SHIPMENT_NUMBER: shipment["shipmentNumber"],
            ATTR_SHIPMENT_DATE: datetime.fromtimestamp(int(shipment["shipmentDate"]) / 1000, datetime.now().astimezone().tzinfo).isoformat(),
            ATTR_STATUS: status,
            ATTR_RAW_STATUS: shipment["shipmentStatus"],
            ATTR_LATEST_EVENT: shipment["lastEvent"]["description"],
            ATTR_LATEST_EVENT_CITY: shipment["lastEvent"]["place"],
            ATTR_LATEST_EVENT_COUNTRY: "FI",
            ATTR_LATEST_EVENT_DATE: shipment["lastEvent"]["time"],
            ATTR_SOURCE: "Matkahuolto"
        }
    )


def map_raw_status(raw_status: int) -> int:
    status = 1  # waiting

    if raw_status >= 60:
        status = 0  # delivered
    elif raw_status >= 50:
        status = 5  # ready for pickup
    elif raw_status >= 40:
        status = 4  # in delivery
    elif raw_status >= 30:
        status = 3  # in transport
    elif raw_status >= 20:
        status = 2  # received

    return status
