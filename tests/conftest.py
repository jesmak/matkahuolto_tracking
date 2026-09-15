"""Shared fixtures: an account, and Matkahuolto's web service with sample shipments."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse

from custom_components.matkahuolto_tracking.const import (
    API_BASE_URL,
    PATH_RECEIVED_SHIPMENTS,
    PATH_REFRESH_TOKEN,
    PATH_USER,
)

USERNAME = "matti.meikalainen@example.com"
ACCESS_TOKEN = "access-token"
REFRESH_TOKEN = "refresh-token"
NEW_ACCESS_TOKEN = "new-access-token"

ENTRY_DATA = {
    "username": USERNAME,
    "access_token": ACCESS_TOKEN,
    "refresh_token": REFRESH_TOKEN,
    "language": "fi",
    "prioritize_undelivered": True,
    "max_shipments": 5,
    "stale_shipment_day_limit": 15,
    "completed_shipment_day_shown": 3,
}

# When the tests run: noon in Finland.
NOW = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)

USER_URL = API_BASE_URL + PATH_USER
SHIPMENTS_URL = API_BASE_URL + PATH_RECEIVED_SHIPMENTS
REFRESH_URL = API_BASE_URL + PATH_REFRESH_TOKEN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Lets Home Assistant load integrations from custom_components/."""


def milliseconds(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def shipment(
    number: str,
    raw_status: int | str,
    event_time: str | None = None,
    *,
    event: str = "Lähetys on noudettavissa",
    delivery_time: int | None = None,
) -> dict[str, Any]:
    """A received shipment shaped like Matkahuolto's. Event times are Finnish time without a zone, as Matkahuolto
    gives them; other times are milliseconds since the epoch."""
    data: dict[str, Any] = {
        "shipmentNumber": number,
        "shipmentStatus": raw_status,
        "senderName": "Verkkokauppa.com",
        "senderCity": "Helsinki",
        "destinationPlaceName": "K-Market Keskusta",
        "receiverCity": "Lappeenranta",
        "shipmentDate": milliseconds(datetime(2026, 9, 14, 6, 0, tzinfo=UTC)),
        "deliveryTime": delivery_time,
    }
    if event_time is not None:
        data["lastEvent"] = {"time": event_time, "description": event, "place": "Lappeenranta"}
    return data


SHIPMENTS = [
    # Ready for pickup since yesterday.
    shipment("MH0001", 55, "2026-09-15T10:00:00"),
    # In transport: the latest change of all.
    shipment("MH0002", 35, "2026-09-16T08:30:00", event="Lähetys on kuljetuksessa"),
    # Delivered two days ago.
    shipment("MH0003", 62, "2026-09-14T09:00:00", event="Lähetys on toimitettu"),
    # Delivered six days ago: hidden.
    shipment("MH0004", 60, "2026-09-10T09:00:00", event="Lähetys on toimitettu"),
    # Stuck in delivery for weeks: hidden.
    shipment("MH0005", 40, "2026-08-20T09:00:00", event="Lähetys on jakelussa"),
    # Delivered this morning, without events.
    shipment("MH0006", "65", delivery_time=milliseconds(datetime(2026, 9, 16, 5, 0, tzinfo=UTC))),
    # No time at all: skipped.
    shipment("MH0007", 20),
]


def answers(*responses: tuple[int, Any]) -> Callable[..., Awaitable[AiohttpClientMockResponse]]:
    """Answers with the given (status, JSON) responses in turn, repeating the last one."""
    remaining = list(responses)

    async def answer(method: str, url: Any, data: Any) -> AiohttpClientMockResponse:
        status, body = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        return AiohttpClientMockResponse(method, url, status=status, json=body)

    return answer


@pytest.fixture
def matkahuolto(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Matkahuolto's web service accepting the tokens."""
    aioclient_mock.get(USER_URL, json={"email": USERNAME})
    aioclient_mock.get(SHIPMENTS_URL, json={"shipments": SHIPMENTS})
    aioclient_mock.post(REFRESH_URL, json={"AuthenticationResult": {"AccessToken": NEW_ACCESS_TOKEN}})
    return aioclient_mock
