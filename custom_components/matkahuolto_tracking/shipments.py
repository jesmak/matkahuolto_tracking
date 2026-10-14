"""Turning the shipments of an account into the sensor's package list.

The packages are in the format package-tracker-card reads, which other tracking
integrations write too, so the card can list them together.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from homeassistant.util import dt as dt_util

from .const import (
    CONF_COMPLETED_SHIPMENT_DAYS_SHOWN,
    CONF_MAX_SHIPMENTS,
    CONF_PICKUP_CODE,
    CONF_PRIORITIZE_UNDELIVERED,
    CONF_STALE_SHIPMENT_DAY_LIMIT,
    DEFAULT_COMPLETED_SHIPMENT_DAYS_SHOWN,
    DEFAULT_MAX_SHIPMENTS,
    DEFAULT_PICKUP_CODE,
    DEFAULT_PRIORITIZE_UNDELIVERED,
    DEFAULT_STALE_SHIPMENT_DAY_LIMIT,
    PICKUP_CODE_CODE,
    TIME_ZONE,
    TRACKING_URL,
)

_LOGGER = logging.getLogger(__name__)

FINNISH_TIME = ZoneInfo(TIME_ZONE)

# Package statuses, as package-tracker-card shows them.
STATUS_DELIVERED = 0
STATUS_WAITING = 1
STATUS_RECEIVED = 2
STATUS_IN_TRANSPORT = 3
STATUS_IN_DELIVERY = 4
STATUS_READY_FOR_PICKUP = 5


@dataclass(frozen=True)
class PackageSettings:
    prioritize_undelivered: bool
    max_shipments: int
    # Undelivered packages whose latest event is older are hidden: some stay "in delivery" for good.
    stale_shipment_day_limit: int
    completed_shipment_days_shown: int
    # none or code: the code collects the package, which not everyone wants on a dashboard. The pickup point itself is
    # always included.
    pickup_code: str

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> PackageSettings:
        return cls(
            prioritize_undelivered=bool(data.get(CONF_PRIORITIZE_UNDELIVERED, DEFAULT_PRIORITIZE_UNDELIVERED)),
            max_shipments=int(data.get(CONF_MAX_SHIPMENTS, DEFAULT_MAX_SHIPMENTS)),
            stale_shipment_day_limit=int(data.get(CONF_STALE_SHIPMENT_DAY_LIMIT, DEFAULT_STALE_SHIPMENT_DAY_LIMIT)),
            completed_shipment_days_shown=int(data.get(CONF_COMPLETED_SHIPMENT_DAYS_SHOWN, DEFAULT_COMPLETED_SHIPMENT_DAYS_SHOWN)),
            pickup_code=str(data.get(CONF_PICKUP_CODE, DEFAULT_PICKUP_CODE)),
        )


@dataclass(frozen=True)
class Packages:
    # When a shipment of the account last changed, hidden ones included. None when there are none.
    latest_change: datetime | None
    # The packages to list, newest first and at most the maximum.
    packages: list[dict[str, Any]]
    # Every package within the age limits, however many: the counts.
    current: list[dict[str, Any]]
    # Every package of the account: what happens to them, also outside the list.
    every: list[dict[str, Any]]


def map_raw_status(raw_status: int) -> int:
    """A package status from Matkahuolto's status code: 60 and above is delivered, 50–59 ready for pickup, and so on."""
    if raw_status >= 60:
        return STATUS_DELIVERED
    if raw_status >= 50:
        return STATUS_READY_FOR_PICKUP
    if raw_status >= 40:
        return STATUS_IN_DELIVERY
    if raw_status >= 30:
        return STATUS_IN_TRANSPORT
    if raw_status >= 20:
        return STATUS_RECEIVED
    return STATUS_WAITING


def build_packages(shipments: Iterable[Mapping[str, Any]], settings: PackageSettings, now: datetime) -> Packages:
    """The packages to list: undelivered ones that aren't stale and recently delivered ones, newest first."""
    latest_change: datetime | None = None
    undelivered: list[tuple[datetime, dict[str, Any]]] = []
    delivered: list[tuple[datetime, dict[str, Any]]] = []

    newest: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for shipment in shipments:
        changed = status_change_time(shipment)
        raw_status = parse_int(shipment.get("shipmentStatus"))
        if changed is None or raw_status is None:
            continue
        if latest_change is None or changed > latest_change:
            latest_change = changed

        status = map_raw_status(raw_status)
        keep_newest(newest, changed, package(shipment, status, changed, settings))

    every = [item for _, item in newest.values()]
    for changed, item in newest.values():
        status = item["status"]
        age_days = (now - changed).days
        if status != STATUS_DELIVERED and age_days <= settings.stale_shipment_day_limit:
            undelivered.append((changed, item))
        elif status == STATUS_DELIVERED and age_days <= settings.completed_shipment_days_shown:
            delivered.append((changed, item))

    undelivered.sort(key=change_time, reverse=True)
    delivered.sort(key=change_time, reverse=True)
    ordered = undelivered + delivered
    if not settings.prioritize_undelivered:
        ordered.sort(key=change_time, reverse=True)
    current = [item for _, item in ordered]
    return Packages(latest_change, current[: settings.max_shipments], current, every)


def keep_newest(newest: dict[str, tuple[datetime, dict[str, Any]]], changed: datetime, item: dict[str, Any]) -> None:
    """Keeps a package by its number, the newest copy when the account lists one twice. One without a number is left out,
    since nothing would tell its updates apart from another's."""
    number = item.get("shipment_number")
    if not number:
        return
    if number not in newest or changed > newest[number][0]:
        newest[number] = (changed, item)


def change_time(item: tuple[datetime, dict[str, Any]]) -> datetime:
    return item[0]


def status_change_time(shipment: Mapping[str, Any]) -> datetime | None:
    """When the shipment last changed: its latest event, or its delivery when it has no events."""
    event = shipment.get("lastEvent")
    if isinstance(event, Mapping) and event.get("time"):
        parsed = parse_time(event["time"])
        if parsed is not None:
            return parsed
        # Matkahuolto has changed the format, and the package would vanish without a word.
        _LOGGER.warning("Matkahuolto gave an event time that can't be read, %r. Using the delivery time instead", event["time"])
    return from_milliseconds(parse_int(shipment.get("deliveryTime")))


def package(shipment: Mapping[str, Any], status: int, changed: datetime, settings: PackageSettings) -> dict[str, Any]:
    event = shipment.get("lastEvent")
    event = event if isinstance(event, Mapping) else {}
    shipment_date = parse_int(shipment.get("shipmentDate"))
    point = shipment.get("pickupPoint") if isinstance(shipment.get("pickupPoint"), Mapping) else {}
    shipment_number = shipment.get("shipmentNumber")
    return {
        "origin": shipment.get("senderName"),
        "origin_city": shipment.get("senderCity"),
        "destination": shipment.get("destinationPlaceName"),
        "destination_city": shipment.get("receiverCity"),
        "shipment_number": shipment_number,
        "shipment_date": iso(from_milliseconds(shipment_date)),
        "status": status,
        "raw_status": shipment.get("shipmentStatus"),
        "latest_event": event.get("description"),
        "latest_event_city": event.get("place"),
        "latest_event_country": "FI",
        "latest_event_date": changed.isoformat(),
        "estimated_delivery": moment(shipment.get("etaDate")),
        "pickup_deadline": moment(shipment.get("storedUntil")),
        "weight": number(shipment.get("shipmentWeight")),
        "package_count": parse_int(shipment.get("parcelCount")),
        "pickup_point": pickup_point(point, shipment),
        # Only a setting that asks for the code shows it: an unknown value keeps it out, as the code is a secret.
        "pickup_code": pickup_code(shipment) if settings.pickup_code == PICKUP_CODE_CODE else None,
        "pickup_qr": None,
        "source": "Matkahuolto",
        "tracking_url": tracking_url(shipment_number),
    }


def moment(value: Any) -> str | None:
    """A time Matkahuolto gives in milliseconds, as an ISO 8601 string."""
    milliseconds = parse_int(value)
    return iso(from_milliseconds(milliseconds))


def iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


def pickup_point(point: Mapping[str, Any], shipment: Mapping[str, Any]) -> dict[str, Any] | None:
    """Where the package is picked up, from the pickup point when there is one, else the destination."""
    found = {
        "name": point.get("officeName") or shipment.get("destinationPlaceName"),
        "street": point.get("officeStreetAddress"),
        "postal_code": point.get("officePostalCode"),
        "city": point.get("officeCity") or shipment.get("receiverCity"),
        "type": point.get("officeType") or shipment.get("destinationPlaceType"),
        "available": None,
    }
    # Without a name it is no pickup point, only the receiver's city: a home delivery has nothing else.
    return found if found["name"] else None


def pickup_code(shipment: Mapping[str, Any]) -> str | None:
    """The code that collects the package."""
    code = shipment.get("deliveryPinCode")
    # Not a plain truth test: a code of 0 is a code.
    return str(code) if code is not None and code != "" else None


def number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_time(value: Any) -> datetime | None:
    """An event time. Times without a zone are Finnish time."""
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=FINNISH_TIME)
    return parsed.astimezone(FINNISH_TIME)


def from_milliseconds(value: int | None) -> datetime | None:
    """A time Matkahuolto gives in milliseconds. One out of range, such as a 9999-12-31 that means no date, is none."""
    if value is None:
        return None
    try:
        return dt_util.utc_from_timestamp(value / 1000).astimezone(FINNISH_TIME)
    except (OverflowError, ValueError, OSError):
        return None


def parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def tracking_url(shipment_number: Any) -> str | None:
    """The carrier's own tracking page for the package."""
    return TRACKING_URL.format(number=quote(str(shipment_number), safe="")) if shipment_number else None
