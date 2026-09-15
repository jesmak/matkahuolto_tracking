"""Turning received shipments into the sensor's packages."""

from __future__ import annotations

from dataclasses import replace

import pytest

from custom_components.matkahuolto_tracking.shipments import Packages, PackageSettings, build_packages, map_raw_status

from .conftest import NOW, SHIPMENTS, shipment

SETTINGS = PackageSettings(
    prioritize_undelivered=True, max_shipments=5, stale_shipment_day_limit=15, completed_shipment_days_shown=3
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
        "source": "Matkahuolto",
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
