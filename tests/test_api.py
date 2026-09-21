"""Matkahuolto's web service: logging in, the access token, refreshing it, and errors."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.matkahuolto_tracking.api import (
    MatkahuoltoAuthError,
    MatkahuoltoClient,
    MatkahuoltoError,
    MatkahuoltoLoginRejectedError,
    log_in,
)

from .conftest import (
    ACCESS_TOKEN,
    AUTH_URL,
    LOGIN,
    NEW_ACCESS_TOKEN,
    NEW_REFRESH_TOKEN,
    PASSWORD,
    REFRESH_TOKEN,
    REFRESH_URL,
    SHIPMENTS,
    SHIPMENTS_URL,
    USERNAME,
    answers,
)


def client(
    hass: HomeAssistant, saved: list[tuple[str, str]] | None = None, password: str | None = None
) -> MatkahuoltoClient:
    def save(access_token: str, refresh_token: str) -> None:
        if saved is not None:
            saved.append((access_token, refresh_token))

    return MatkahuoltoClient(
        async_get_clientsession(hass), ACCESS_TOKEN, REFRESH_TOKEN, "fi", save, USERNAME if password else None, password
    )


async def test_logging_in_as_the_app(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(AUTH_URL, json=LOGIN)

    assert await log_in(async_get_clientsession(hass), USERNAME, PASSWORD) == (NEW_ACCESS_TOKEN, NEW_REFRESH_TOKEN)

    [(_method, _url, body, headers)] = aioclient_mock.mock_calls
    assert body == {"username": USERNAME, "password": PASSWORD}, "no reCAPTCHA, unlike the website"
    assert headers["User-Agent"].startswith("okhttp/")
    assert headers["Paketit-Client"].startswith("android/")


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, MatkahuoltoAuthError), (400, MatkahuoltoLoginRejectedError), (503, MatkahuoltoError)],
)
async def test_a_login_that_fails(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int, error: type[Exception]
) -> None:
    aioclient_mock.post(AUTH_URL, status=status, text="Invalid request")
    with pytest.raises(error):
        await log_in(async_get_clientsession(hass), USERNAME, PASSWORD)


async def test_a_login_answer_without_tokens(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(AUTH_URL, json={"ChallengeParameters": {}})
    with pytest.raises(MatkahuoltoError) as error:
        await log_in(async_get_clientsession(hass), USERNAME, PASSWORD)
    assert not isinstance(error.value, MatkahuoltoAuthError)


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
    saved: list[tuple[str, str]] = []
    matkahuolto = client(hass, saved)

    assert len(await matkahuolto.received_shipments()) == len(SHIPMENTS)
    assert matkahuolto.access_token == NEW_ACCESS_TOKEN
    assert saved == [(NEW_ACCESS_TOKEN, REFRESH_TOKEN)], "the new access token is handed over for saving"

    _expired, refresh, retry = aioclient_mock.mock_calls
    assert refresh[2] == {"accessToken": ACCESS_TOKEN}
    assert refresh[3]["Authorization"] == REFRESH_TOKEN
    assert retry[3]["Authorization"] == NEW_ACCESS_TOKEN


async def test_a_refused_refresh_token_logs_in_again(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(SHIPMENTS_URL, side_effect=answers((401, None), (200, {"shipments": SHIPMENTS})))
    aioclient_mock.post(REFRESH_URL, status=401)
    aioclient_mock.post(AUTH_URL, json=LOGIN)
    saved: list[tuple[str, str]] = []
    matkahuolto = client(hass, saved, PASSWORD)

    assert len(await matkahuolto.received_shipments()) == len(SHIPMENTS)
    assert (matkahuolto.access_token, matkahuolto.refresh_token) == (NEW_ACCESS_TOKEN, NEW_REFRESH_TOKEN)
    assert saved == [(NEW_ACCESS_TOKEN, NEW_REFRESH_TOKEN)], "both new tokens are handed over for saving"
    assert aioclient_mock.mock_calls[-1][3]["Authorization"] == NEW_ACCESS_TOKEN


async def test_a_refused_password_needs_a_new_one(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(SHIPMENTS_URL, status=401)
    aioclient_mock.post(REFRESH_URL, status=401)
    aioclient_mock.post(AUTH_URL, status=401)
    with pytest.raises(MatkahuoltoAuthError):
        await client(hass, password=PASSWORD).received_shipments()


async def test_a_refused_refresh_token_without_a_password_needs_one(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(SHIPMENTS_URL, status=401)
    aioclient_mock.post(REFRESH_URL, status=401)
    with pytest.raises(MatkahuoltoAuthError):
        await client(hass).received_shipments()
    assert all(str(call[1]) != AUTH_URL for call in aioclient_mock.mock_calls)


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
