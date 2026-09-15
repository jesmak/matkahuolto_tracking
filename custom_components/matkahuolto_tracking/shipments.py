"""Turning the shipments of an account into the sensor's package list.

The packages have the same attributes and statuses as in Posti package
tracking, so package-tracker-card can list packages from both.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.util import dt as dt_util

from .const import (
    CONF_COMPLETED_SHIPMENT_DAYS_SHOWN,
    CONF_MAX_SHIPMENTS,
    CONF_PRIORITIZE_UNDELIVERED,
    CONF_STALE_SHIPMENT_DAY_LIMIT,
    DEFAULT_COMPLETED_SHIPMENT_DAYS_SHOWN,
    DEFAULT_MAX_SHIPMENTS,
    DEFAULT_PRIORITIZE_UNDELIVERED,
    DEFAULT_STALE_SHIPMENT_DAY_LIMIT,
    TIME_ZONE,
)

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

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> PackageSettings:
        return cls(
            prioritize_undelivered=bool(data.get(CONF_PRIORITIZE_UNDELIVERED, DEFAULT_PRIORITIZE_UNDELIVERED)),
            max_shipments=int(data.get(CONF_MAX_SHIPMENTS, DEFAULT_MAX_SHIPMENTS)),
            stale_shipment_day_limit=int(data.get(CONF_STALE_SHIPMENT_DAY_LIMIT, DEFAULT_STALE_SHIPMENT_DAY_LIMIT)),
            completed_shipment_days_shown=int(
                data.get(CONF_COMPLETED_SHIPMENT_DAYS_SHOWN, DEFAULT_COMPLETED_SHIPMENT_DAYS_SHOWN)
            ),
        )


@dataclass(frozen=True)
class Packages:
    # When a shipment of the account last changed, hidden ones included. None when there are none.
    latest_change: datetime | None
    packages: list[dict[str, Any]]


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

    for shipment in shipments:
        changed = status_change_time(shipment)
        raw_status = parse_int(shipment.get("shipmentStatus"))
        if changed is None or raw_status is None:
            continue
        if latest_change is None or changed > latest_change:
            latest_change = changed

        status = map_raw_status(raw_status)
        age_days = (now - changed).days
        if status != STATUS_DELIVERED and age_days <= settings.stale_shipment_day_limit:
            undelivered.append((changed, package(shipment, status, changed)))
        elif status == STATUS_DELIVERED and age_days <= settings.completed_shipment_days_shown:
            delivered.append((changed, package(shipment, status, changed)))

    undelivered.sort(key=change_time, reverse=True)
    delivered.sort(key=change_time, reverse=True)
    ordered = undelivered + delivered
    if not settings.prioritize_undelivered:
        ordered.sort(key=change_time, reverse=True)
    return Packages(latest_change, [item for _, item in ordered[: settings.max_shipments]])


def change_time(item: tuple[datetime, dict[str, Any]]) -> datetime:
    return item[0]


def status_change_time(shipment: Mapping[str, Any]) -> datetime | None:
    """When the shipment last changed: its latest event, or its delivery when it has no events."""
    event = shipment.get("lastEvent")
    if isinstance(event, Mapping) and event.get("time"):
        return parse_time(event["time"])
    delivery_time = parse_int(shipment.get("deliveryTime"))
    return from_milliseconds(delivery_time) if delivery_time is not None else None


def package(shipment: Mapping[str, Any], status: int, changed: datetime) -> dict[str, Any]:
    event = shipment.get("lastEvent")
    event = event if isinstance(event, Mapping) else {}
    shipment_date = parse_int(shipment.get("shipmentDate"))
    return {
        "origin": shipment.get("senderName"),
        "origin_city": shipment.get("senderCity"),
        "destination": shipment.get("destinationPlaceName"),
        "destination_city": shipment.get("receiverCity"),
        "shipment_number": shipment.get("shipmentNumber"),
        "shipment_date": from_milliseconds(shipment_date).isoformat() if shipment_date is not None else None,
        "status": status,
        "raw_status": shipment.get("shipmentStatus"),
        "latest_event": event.get("description"),
        "latest_event_city": event.get("place"),
        "latest_event_country": "FI",
        "latest_event_date": changed.isoformat(),
        "source": "Matkahuolto",
    }


def parse_time(value: Any) -> datetime | None:
    """An event time. Times without a zone are Finnish time."""
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=FINNISH_TIME)
    return parsed.astimezone(FINNISH_TIME)


def from_milliseconds(value: int) -> datetime:
    return dt_util.utc_from_timestamp(value / 1000).astimezone(FINNISH_TIME)


def parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
