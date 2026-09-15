"""Matkahuolto's web service: the access token, refreshing it, and errors."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.matkahuolto_tracking.api import MatkahuoltoAuthError, MatkahuoltoClient, MatkahuoltoError

from .conftest import ACCESS_TOKEN, NEW_ACCESS_TOKEN, REFRESH_TOKEN, REFRESH_URL, SHIPMENTS, SHIPMENTS_URL, answers


def client(hass: HomeAssistant, saved: list[str] | None = None) -> MatkahuoltoClient:
    return MatkahuoltoClient(
        async_get_clientsession(hass), ACCESS_TOKEN, REFRESH_TOKEN, "fi", saved.append if saved is not None else None
    )


async def test_shipments_are_fetched_with_the_access_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(SHIPMENTS_URL, json={"shipments": SHIPMENTS})
    assert len(await client(hass).received_shipments()) == len(SHIPMENTS)

    [(_method, url, _data, headers)] = aioclient_mock.mock_calls
    assert url.query["language"] == "fi"
    assert headers["Authorization"] == ACCESS_TOKEN


async def test_an_expired_access_token_is_refreshed(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(SHIPMENTS_URL, side_effect=answers((401, None), (200, {"shipments": SHIPMENTS})))
    aioclient_mock.post(REFRESH_URL, json={"AuthenticationResult": {"AccessToken": NEW_ACCESS_TOKEN}})
    saved: list[str] = []
    matkahuolto = client(hass, saved)

    assert len(await matkahuolto.received_shipments()) == len(SHIPMENTS)
    assert matkahuolto.access_token == NEW_ACCESS_TOKEN
    assert saved == [NEW_ACCESS_TOKEN], "the new access token is handed over for saving"

    _expired, refresh, retry = aioclient_mock.mock_calls
    assert refresh[2] == {"accessToken": ACCESS_TOKEN}
    assert refresh[3]["Authorization"] == REFRESH_TOKEN
    assert retry[3]["Authorization"] == NEW_ACCESS_TOKEN


async def test_a_refused_refresh_token_needs_new_tokens(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(SHIPMENTS_URL, status=401)
    aioclient_mock.post(REFRESH_URL, status=401)
    with pytest.raises(MatkahuoltoAuthError):
        await client(hass).received_shipments()


async def test_a_refreshed_token_that_is_refused_too_needs_new_tokens(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(SHIPMENTS_URL, status=401)
    aioclient_mock.post(REFRESH_URL, json={"AuthenticationResult": {"AccessToken": NEW_ACCESS_TOKEN}})
    with pytest.raises(MatkahuoltoAuthError):
        await client(hass).received_shipments()


@pytest.mark.parametrize(("shipments_status", "refresh_status"), [(503, None), (401, 502)])
async def test_server_errors_are_not_token_problems(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, shipments_status: int, refresh_status: int | None
) -> None:
    aioclient_mock.get(SHIPMENTS_URL, status=shipments_status)
    if refresh_status is not None:
        aioclient_mock.post(REFRESH_URL, status=refresh_status)
    with pytest.raises(MatkahuoltoError) as error:
        await client(hass).received_shipments()
    assert not isinstance(error.value, MatkahuoltoAuthError)


async def test_connection_errors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(SHIPMENTS_URL, exc=aiohttp.ClientError("connection reset"))
    with pytest.raises(MatkahuoltoError):
        await client(hass).received_shipments()


async def test_an_unexpected_response(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(SHIPMENTS_URL, json={"something": "else"})
    with pytest.raises(MatkahuoltoError):
        await client(hass).received_shipments()
