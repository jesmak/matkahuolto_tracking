"""Turning received shipments into the sensor's packages."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from custom_components.matkahuolto_tracking import shipments as shipments_module
from custom_components.matkahuolto_tracking.shipments import Packages, PackageSettings, build_packages, map_raw_status, parse_int

from .conftest import NOW, SHIPMENTS, milliseconds, shipment

SETTINGS = PackageSettings(
    prioritize_undelivered=True,
    max_shipments=5,
    max_outgoing_shipments=5,
    stale_shipment_day_limit=15,
    completed_shipment_days_shown=3,
    pickup_code="none",
)


def numbers(packages: Packages) -> list[str]:
    return [package["shipment_number"] for package in packages.packages]


@pytest.mark.parametrize(("raw_status", "status"), [(0, 1), (19, 1), (20, 2), (35, 3), (40, 4), (55, 5), (60, 0), (99, 0)])
def test_matkahuolto_status_codes(raw_status: int, status: int) -> None:
    assert map_raw_status(raw_status) == status


def test_undelivered_packages_come_first_and_old_ones_are_hidden() -> None:
    packages = build_packages(SHIPMENTS, SETTINGS, NOW)
    assert numbers(packages) == ["MH0002", "MH0001", "MH0007", "MH0006", "MH0003"]
    assert packages.latest_change.isoformat() == "2026-09-16T08:30:00+03:00"


def test_newest_first_when_undelivered_packages_are_not_prioritised() -> None:
    settings = replace(SETTINGS, prioritize_undelivered=False, max_shipments=3)
    assert numbers(build_packages(SHIPMENTS, settings, NOW)) == ["MH0002", "MH0006", "MH0001"]


def test_package_attributes() -> None:
    _, ready, _announced, delivered_without_events, _ = build_packages(SHIPMENTS, SETTINGS, NOW).packages
    assert ready == {
        "origin": "Example Shop",
        "origin_city": "Helsinki",
        "recipient": None,
        "destination": "Example Market Keskusta",
        "destination_city": "Lappeenranta",
        "shipment_number": "MH0001",
        "shipment_date": "2026-09-14T09:00:00+03:00",
        "status": 5,
        "raw_status": 55,
        "direction": "incoming",
        "latest_event": "Lähetys on noudettavissa",
        "latest_event_city": "Lappeenranta",
        "latest_event_country": "FI",
        "latest_event_date": "2026-09-15T10:00:00+03:00",
        "estimated_delivery": None,
        "pickup_deadline": None,
        "weight": None,
        "package_count": None,
        # The destination stands in for the pickup point, which is always included.
        "pickup_point": {
            "name": "Example Market Keskusta",
            "street": None,
            "postal_code": None,
            "city": "Lappeenranta",
            "type": None,
            "available": None,
        },
        "pickup_code": None,
        "pickup_qr": None,
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
                "officeStreetAddress": "Esimerkkikatu 1",
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


def test_the_pickup_point_is_always_there_but_the_code_only_when_asked_for() -> None:
    [package] = build_packages([with_details()], SETTINGS, NOW).packages
    assert package["pickup_point"]["name"] == "Matkahuolto Keskusta"
    assert package["pickup_code"] is None
    assert package["pickup_qr"] is None


def test_the_pickup_point_and_its_code_when_asked_for() -> None:
    settings = replace(SETTINGS, pickup_code="code")
    [package] = build_packages([with_details()], settings, NOW).packages
    assert package["pickup_point"] == {
        "name": "Matkahuolto Keskusta",
        "street": "Esimerkkikatu 1",
        "postal_code": "53100",
        "city": "Lappeenranta",
        "type": "SERVICE_POINT",
        "available": None,
    }
    assert package["pickup_code"] == "12345678"


def test_the_destination_stands_in_for_a_missing_pickup_point() -> None:
    settings = replace(SETTINGS, pickup_code="code")
    plain = shipment("MH0021", 55, "2026-09-16T08:00:00")
    [package] = build_packages([plain], settings, NOW).packages
    assert package["pickup_point"] == {
        "name": "Example Market Keskusta",
        "street": None,
        "postal_code": None,
        "city": "Lappeenranta",
        "type": None,
        "available": None,
    }
    assert package["pickup_code"] is None


def test_a_home_delivery_has_no_pickup_point() -> None:
    home = {key: value for key, value in shipment("MH0022", 40, "2026-09-16T08:00:00").items() if key != "destinationPlaceName"}
    [package] = build_packages([home], SETTINGS, NOW).packages
    assert package["pickup_point"] is None, "the receiver's city alone is no pickup point"


def test_the_counts_and_events_see_every_package_not_only_the_listed_ones() -> None:
    moving = [shipment(f"MH03{n}", 35, f"2026-09-16T0{n}:00:00") for n in range(1, 4)]
    stale = shipment("MH0399", 35, "2026-08-01T08:00:00")
    packages = build_packages([*moving, stale], replace(SETTINGS, max_shipments=2), NOW)
    assert len(packages.packages) == 2
    assert len(packages.current) == 3, "a count covers all of them, but not one gone stale"
    assert len(packages.every) == 4, "events follow every package, stale ones too"


@pytest.mark.parametrize("setting", ["None", "codes", ""])
def test_a_setting_that_is_not_known_keeps_the_code_out(setting: str) -> None:
    [package] = build_packages([with_details()], replace(SETTINGS, pickup_code=setting), NOW).packages
    assert package["pickup_code"] is None


def test_a_package_listed_twice_is_kept_once_as_its_newest_copy() -> None:
    newer = shipment("MH0600", 55, "2026-09-16T11:30:00")
    older = shipment("MH0600", 35, "2026-09-16T08:30:00")
    for twice in ([newer, older], [older, newer]):
        assert [package["status"] for package in build_packages(twice, SETTINGS, NOW).every.values()] == [5]


def test_a_package_without_a_number_is_left_out() -> None:
    nameless = {key: value for key, value in shipment("MH0601", 35, "2026-09-16T08:30:00").items() if key != "shipmentNumber"}
    assert build_packages([nameless], SETTINGS, NOW).every == {}


def test_an_event_time_that_cannot_be_read_falls_back_to_the_delivery(caplog: pytest.LogCaptureFixture) -> None:
    changed = {**shipment("MH0800", 60, "2026-09-16T08:30:00"), "deliveryTime": milliseconds(datetime(2026, 9, 16, 6, 0, tzinfo=UTC))}
    changed["lastEvent"]["time"] = 1789000000000
    [package] = build_packages([changed], SETTINGS, NOW).packages
    assert package["latest_event_date"] == "2026-09-16T09:00:00+03:00"
    assert "can't be read" in caplog.text, "a changed format is said out loud, not swallowed"


def test_a_time_out_of_range_is_left_empty_and_the_package_stays() -> None:
    sentinel = {**shipment("MH0801", 35, "2026-09-16T08:30:00"), "etaDate": 253402300799999, "storedUntil": 10**20}
    [package] = build_packages([sentinel], SETTINGS, NOW).packages
    assert package["estimated_delivery"] is None
    assert package["pickup_deadline"] is None


def test_a_pickup_code_of_zero_is_a_code() -> None:
    zero = {**shipment("MH0802", 55, "2026-09-16T08:30:00"), "deliveryPinCode": 0}
    [package] = build_packages([zero], replace(SETTINGS, pickup_code="code"), NOW).packages
    assert package["pickup_code"] == "0"


def test_the_day_limits_count_the_hours_too() -> None:
    # Delivered three days and an hour ago is past a limit of three days.
    late = (NOW - timedelta(days=3, hours=1)).astimezone(shipments_module.FINNISH_TIME).replace(tzinfo=None).isoformat()
    delivered = shipment("MH0030", 62, late, event="Lähetys on toimitettu")
    assert build_packages([delivered], SETTINGS, NOW).packages == []
    assert numbers(build_packages([delivered], replace(SETTINGS, completed_shipment_days_shown=4), NOW)) == ["MH0030"]


def test_an_odd_number_takes_nothing_down() -> None:
    assert parse_int(float("inf")) is None
    odd = {**shipment("MH0031", 35), "deliveryTime": float("inf"), "lastEvent": {"time": "9999-12-31T23:59:59+14:00"}}
    build_packages([odd], SETTINGS, NOW)


def test_a_number_given_as_a_number_is_text() -> None:
    # package-tracker-card leaves out a package whose number isn't text.
    [package] = build_packages([{**shipment("MH0032", 35, "2026-09-16T08:30:00"), "shipmentNumber": 123456}], SETTINGS, NOW).packages
    assert package["shipment_number"] == "123456"


def test_an_unreadable_time_is_warned_of_once(caplog: pytest.LogCaptureFixture) -> None:
    odd = shipment("MH0033", 35, "the 16th of September")
    build_packages([odd], SETTINGS, NOW)
    build_packages([odd], SETTINGS, NOW)
    assert caplog.text.count("can't be read") == 1


def sent(number: str, raw_status: int, event_time: str) -> dict[str, Any]:
    """A shipment the account sent, to a made-up recipient."""
    return {**shipment(number, raw_status, event_time), "senderName": "Matti Meikäläinen", "receiverName": "Maija Mallikas"}


def test_a_sent_package_says_so_and_names_its_recipient() -> None:
    to_home = {**sent("MH1001", 35, "2026-09-16T08:30:00"), "destinationPlaceName": None}
    [package] = build_packages([], SETTINGS, NOW, [to_home]).packages
    assert package["direction"] == "outgoing"
    assert (package["origin"], package["origin_city"]) == (None, None), "its sender is the user"
    assert package["recipient"] == "Maija Mallikas", "who it goes to, in its own key"
    assert package["destination"] is None, "a place, not the recipient"
    [package] = build_packages([], SETTINGS, NOW, [sent("MH1002", 55, "2026-09-16T08:30:00")]).packages
    assert package["destination"] == "Example Market Keskusta", "the pickup point when it has one"


def test_each_direction_is_listed_up_to_its_own_maximum() -> None:
    received = [shipment(f"MH200{n}", 35, f"2026-09-16T0{n}:00:00") for n in range(1, 4)]
    outgoing = [sent(f"MH300{n}", 35, f"2026-09-16T0{n}:30:00") for n in range(1, 4)]
    packages = build_packages(received, replace(SETTINGS, max_shipments=2, max_outgoing_shipments=1), NOW, outgoing)
    assert numbers(packages) == ["MH3003", "MH2003", "MH2002"], "newest first, two received and one sent"
    assert len(packages.current) == 6, "the counts see all of them"


def test_a_maximum_of_0_leaves_that_direction_out_altogether() -> None:
    received = shipment("MH4001", 35, "2026-09-16T05:00:00")
    outgoing = sent("MH4002", 35, "2026-09-16T08:00:00")
    packages = build_packages([received], replace(SETTINGS, max_outgoing_shipments=0), NOW, [outgoing])
    assert numbers(packages) == ["MH4001"]
    assert list(packages.every) == ["MH4001"], "no events for it either"
    assert packages.latest_change.isoformat() == "2026-09-16T05:00:00+03:00", "nor does it change the sensor's time"


def test_a_package_sent_to_oneself_is_a_received_one() -> None:
    # Even when its sent copy is newer, as when it moves on between the two requests.
    received = shipment("MH5001", 35, "2026-09-16T08:30:00")
    sent_copy = shipment("MH5001", 55, "2026-09-16T08:31:00")
    [package] = build_packages([received], SETTINGS, NOW, [sent_copy]).packages
    assert (package["direction"], package["status"]) == ("incoming", 3)
    # And when received packages are left out, it is left out too, not listed as a sent one.
    assert build_packages([received], replace(SETTINGS, max_shipments=0), NOW, [sent_copy]).every == {}
