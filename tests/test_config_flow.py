"""Adding an account by logging in, logging in again, and changing its settings."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.matkahuolto_tracking.const import DOMAIN

from .conftest import (
    AUTH_URL,
    ENTRY_DATA,
    LOGIN,
    NEW_ACCESS_TOKEN,
    NEW_REFRESH_TOKEN,
    PASSWORD,
    SENT_URL,
    SHIPMENTS,
    SHIPMENTS_URL,
    SUBJECT,
    USER_URL,
    USERNAME,
)

SETTINGS = {
    "language": "fi",
    "prioritize_undelivered": True,
    "max_shipments": 5.0,
    "max_outgoing_shipments": 5.0,
    "stale_shipment_day_limit": 15.0,
    "completed_shipment_day_shown": 3.0,
    "pickup_code": "none",
}
NEW_SETTINGS = {
    "language": "en",
    "prioritize_undelivered": False,
    "max_shipments": 10.0,
    "max_outgoing_shipments": 0.0,
    "stale_shipment_day_limit": 30.0,
    "completed_shipment_day_shown": 1.0,
    "pickup_code": "code",
}
STORED_NEW_SETTINGS = {
    "language": "en",
    "prioritize_undelivered": False,
    "max_shipments": 10,
    "max_outgoing_shipments": 0,
    "stale_shipment_day_limit": 30,
    "completed_shipment_day_shown": 1,
    "pickup_code": "code",
}
NEW_TOKENS = {"access_token": NEW_ACCESS_TOKEN, "refresh_token": NEW_REFRESH_TOKEN}
# What a login again saves: the tokens, the account's id, and the email it logged in with.
NEW_LOGIN = {**NEW_TOKENS, "subject": SUBJECT, "email": USERNAME}


def expect_login(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(AUTH_URL, json=LOGIN)
    aioclient_mock.get(USER_URL, json={"email": USERNAME})
    aioclient_mock.get(SHIPMENTS_URL, json={"shipments": SHIPMENTS})
    aioclient_mock.get(SENT_URL, json={"shipments": []})


def account(hass: HomeAssistant, **data: object) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title=USERNAME, version=2, minor_version=4, unique_id=USERNAME, data={**ENTRY_DATA, **data})
    entry.add_to_hass(hass)
    return entry


async def log_in(hass: HomeAssistant, username: str = f" {USERNAME} ", password: str = PASSWORD) -> dict:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"username": username, "password": password})


async def test_adding_an_account(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    expect_login(aioclient_mock)

    result = await log_in(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "settings"
    assert result["description_placeholders"] == {"username": USERNAME}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], SETTINGS)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == USERNAME
    assert result["data"] == {**ENTRY_DATA, **NEW_TOKENS, "subject": SUBJECT}
    assert result["result"].unique_id == USERNAME
    await hass.async_block_till_done()
    assert hass.states.get("sensor.matkahuolto_matti_meikalainen_example_com") is not None


async def test_a_wrong_password(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(AUTH_URL, status=401)

    result = await log_in(hass)

    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_matkahuolto_turns_the_login_away(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(AUTH_URL, status=400, text="Invalid request")

    result = await log_in(hass)

    assert result["errors"] == {"base": "login_rejected"}


async def test_matkahuolto_cannot_be_reached(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(AUTH_URL, status=503)

    result = await log_in(hass)

    assert result["errors"] == {"base": "cannot_connect"}


async def test_an_account_is_added_only_once(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    account(hass)

    result = await log_in(hass, username=USERNAME.upper())

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert aioclient_mock.call_count == 0


async def test_logging_in_again_when_the_login_stops_working(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    expect_login(aioclient_mock)
    entry = account(hass, password="old-password", access_token="expired", refresh_token="expired")

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["username"] == USERNAME
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"username": USERNAME, "password": PASSWORD})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {**ENTRY_DATA, **NEW_LOGIN}


async def test_a_wrong_password_when_logging_in_again(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(AUTH_URL, status=401)
    entry = account(hass, access_token="expired", refresh_token="expired")

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"username": USERNAME, "password": "wrong"})

    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["refresh_token"] == "expired"


async def start_reconfigure(hass: HomeAssistant, entry: MockConfigEntry, choice: str) -> dict:
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["reconfigure_settings", "reconfigure_login"]
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": choice})


async def test_changing_the_settings(hass: HomeAssistant, matkahuolto: AiohttpClientMocker) -> None:
    entry = account(hass)

    result = await start_reconfigure(hass, entry, "reconfigure_settings")
    assert result["step_id"] == "reconfigure_settings"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], NEW_SETTINGS)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {**ENTRY_DATA, **STORED_NEW_SETTINGS}


async def test_a_new_password_from_reconfigure(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    expect_login(aioclient_mock)
    entry = account(hass, password="old-password")

    result = await start_reconfigure(hass, entry, "reconfigure_login")
    assert result["step_id"] == "reconfigure_login"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"username": USERNAME, "password": PASSWORD})
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {**ENTRY_DATA, **NEW_LOGIN}


async def test_logging_in_again_offers_the_email_in_use(hass: HomeAssistant) -> None:
    entry = account(hass, email="matti.uusi@example.com")

    result = await entry.start_reauth_flow(hass)

    [field] = [key for key in result["data_schema"].schema if key == "username"]
    assert field.description == {"suggested_value": "matti.uusi@example.com"}
    assert result["description_placeholders"]["username"] == "matti.uusi@example.com"


async def test_logging_in_again_after_the_email_changed(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    expect_login(aioclient_mock)
    entry = account(hass, subject=SUBJECT, access_token="expired", refresh_token="expired")

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": " matti.uusi@example.com ", "password": PASSWORD}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reauth_successful"
    # The entities keep their ids, built from the email the account was added with. The new one logs in.
    assert entry.data == {**ENTRY_DATA, **NEW_LOGIN, "email": "matti.uusi@example.com"}
    assert entry.title == "matti.uusi@example.com"
    [(_method, _url, posted, _headers)] = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert posted["username"] == "matti.uusi@example.com"


async def test_logging_in_again_as_another_account(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    expect_login(aioclient_mock)
    entry = account(hass, subject="someone-else", access_token="expired", refresh_token="expired")

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"username": USERNAME, "password": PASSWORD})

    assert result["errors"] == {"base": "wrong_account"}
    assert entry.data["refresh_token"] == "expired"


async def test_an_entry_without_an_id_is_matched_by_its_email(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    expect_login(aioclient_mock)
    entry = account(hass, access_token="expired", refresh_token="expired")

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "someone.else@example.com", "password": PASSWORD}
    )

    assert result["errors"] == {"base": "wrong_account"}
