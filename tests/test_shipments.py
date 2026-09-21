"""Turning received shipments into the sensor's packages."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from custom_components.matkahuolto_tracking.shipments import Packages, PackageSettings, build_packages, map_raw_status

from .conftest import NOW, SHIPMENTS, milliseconds, shipment

SETTINGS = PackageSettings(
    prioritize_undelivered=True,
    max_shipments=5,
    stale_shipment_day_limit=15,
    completed_shipment_days_shown=3,
    include_pickup_details=False,
)


def numbers(packages: Packages) -> list[str]:
    return [package["shipment_number"] for package in packages.packages]


@pytest.mark.parametrize(
    ("raw_status", "status"), [(0, 1), (19, 1), (20, 2), (35, 3), (40, 4), (55, 5), (60, 0), (99, 0)]
)
def test_matkahuolto_status_codes(raw_status: int, status: int) -> None:
    assert map_raw_status(raw_status) == status


def test_undelivered_packages_come_first_and_old_ones_are_hidden() -> None:
    packages = build_packages(SHIPMENTS, SETTINGS, NOW)
    assert numbers(packages) == ["MH0002", "MH0001", "MH0006", "MH0003"]
    assert packages.latest_change.isoformat() == "2026-09-16T08:30:00+03:00"


def test_newest_first_when_undelivered_packages_are_not_prioritised() -> None:
    settings = replace(SETTINGS, prioritize_undelivered=False, max_shipments=3)
    assert numbers(build_packages(SHIPMENTS, settings, NOW)) == ["MH0002", "MH0006", "MH0001"]


def test_package_attributes() -> None:
    _, ready, delivered_without_events, _ = build_packages(SHIPMENTS, SETTINGS, NOW).packages
    assert ready == {
        "origin": "Verkkokauppa.com",
        "origin_city": "Helsinki",
        "destination": "K-Market Keskusta",
        "destination_city": "Lappeenranta",
        "shipment_number": "MH0001",
        "shipment_date": "2026-09-14T09:00:00+03:00",
        "status": 5,
        "raw_status": 55,
        "latest_event": "Lähetys on noudettavissa",
        "latest_event_city": "Lappeenranta",
        "latest_event_country": "FI",
        "latest_event_date": "2026-09-15T10:00:00+03:00",
        "estimated_delivery": None,
        "pickup_deadline": None,
        "weight": None,
        "package_count": None,
        "pickup_point": None,
        "pickup_code": None,
        "source": "Matkahuolto",
        "tracking_url": "https://www.matkahuolto.fi/seuranta?parcelNumber=MH0001",
    }
    # Without events, the delivery is the latest change.
    assert delivered_without_events["status"] == 0
    assert delivered_without_events["latest_event"] is None
    assert delivered_without_events["latest_event_date"] == "2026-09-16T08:00:00+03:00"


def test_times_with_a_zone_are_shown_in_finnish_time() -> None:
    [package] = build_packages([shipment("MH0008", 30, "2026-09-16T05:30:00+00:00")], SETTINGS, NOW).packages
    assert package["latest_event_date"] == "2026-09-16T08:30:00+03:00"


def test_an_account_without_shipments() -> None:
    packages = build_packages([], SETTINGS, NOW)
    assert (packages.latest_change, packages.packages) == (None, [])


def with_details(**changes: Any) -> dict[str, Any]:
    """A shipment with the fields Matkahuolto fills in besides the events."""
    data = shipment("MH0020", 55, "2026-09-16T08:00:00")
    data.update(
        {
            "etaDate": milliseconds(datetime(2026, 9, 17, 7, 0, tzinfo=UTC)),
            "storedUntil": milliseconds(datetime(2026, 9, 23, 20, 59, tzinfo=UTC)),
            "shipmentWeight": 2.4,
            "parcelCount": 2,
            "deliveryPinCode": "12345678",
            "pickupPoint": {
                "officeName": "Matkahuolto Keskusta",
                "officeStreetAddress": "Kauppakatu 1",
                "officePostalCode": "53100",
                "officeCity": "Lappeenranta",
                "officeType": "SERVICE_POINT",
            },
            **changes,
        }
    )
    return data


def test_a_package_carries_what_matkahuolto_knows_of_it() -> None:
    [package] = build_packages([with_details()], SETTINGS, NOW).packages
    assert package["estimated_delivery"] == "2026-09-17T10:00:00+03:00"
    assert package["pickup_deadline"] == "2026-09-23T23:59:00+03:00"
    assert package["weight"] == 2.4
    assert package["package_count"] == 2


def test_the_pickup_point_and_its_code_are_left_out_unless_asked_for() -> None:
    [package] = build_packages([with_details()], SETTINGS, NOW).packages
    assert package["pickup_point"] is None
    assert package["pickup_code"] is None


def test_the_pickup_point_and_its_code_when_asked_for() -> None:
    settings = replace(SETTINGS, include_pickup_details=True)
    [package] = build_packages([with_details()], settings, NOW).packages
    assert package["pickup_point"] == {
        "name": "Matkahuolto Keskusta",
        "street": "Kauppakatu 1",
        "postal_code": "53100",
        "city": "Lappeenranta",
        "type": "SERVICE_POINT",
        "available": None,
    }
    assert package["pickup_code"] == "12345678"


def test_the_destination_stands_in_for_a_missing_pickup_point() -> None:
    settings = replace(SETTINGS, include_pickup_details=True)
    plain = shipment("MH0021", 55, "2026-09-16T08:00:00")
    [package] = build_packages([plain], settings, NOW).packages
    assert package["pickup_point"] == {
        "name": "K-Market Keskusta",
        "street": None,
        "postal_code": None,
        "city": "Lappeenranta",
        "type": None,
        "available": None,
    }
    assert package["pickup_code"] is None
