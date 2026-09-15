"""Adding an account, and changing its tokens and settings."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.matkahuolto_tracking.const import DOMAIN

from .conftest import (
    ACCESS_TOKEN,
    ENTRY_DATA,
    NEW_ACCESS_TOKEN,
    REFRESH_TOKEN,
    REFRESH_URL,
    SHIPMENTS,
    SHIPMENTS_URL,
    USER_URL,
    USERNAME,
    answers,
)

# As typed and pasted: spaces around the email address, and tokens copied with their quotation marks.
FORM = {
    **ENTRY_DATA,
    "username": f" {USERNAME} ",
    "access_token": f' "{ACCESS_TOKEN}" ',
    "refresh_token": f"{REFRESH_TOKEN}\n",
    "max_shipments": 5.0,
    "stale_shipment_day_limit": 15.0,
    "completed_shipment_day_shown": 3.0,
}


def account(hass: HomeAssistant, **data: object) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, title=USERNAME, version=2, minor_version=2, unique_id=USERNAME, data={**ENTRY_DATA, **data}
    )
    entry.add_to_hass(hass)
    return entry


async def submit(hass: HomeAssistant, form: dict) -> dict:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], form)


async def test_adding_an_account(hass: HomeAssistant, matkahuolto: AiohttpClientMocker) -> None:
    result = await submit(hass, FORM)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == USERNAME
    assert result["data"] == ENTRY_DATA
    assert result["result"].unique_id == USERNAME
    await hass.async_block_till_done()
    assert hass.states.get("sensor.matkahuolto_matti_meikalainen_example_com") is not None


async def test_an_expired_access_token_is_refreshed_when_adding(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(USER_URL, side_effect=answers((401, None), (200, {"email": USERNAME})))
    aioclient_mock.post(REFRESH_URL, json={"AuthenticationResult": {"AccessToken": NEW_ACCESS_TOKEN}})
    aioclient_mock.get(SHIPMENTS_URL, json={"shipments": SHIPMENTS})

    result = await submit(hass, FORM)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["access_token"] == NEW_ACCESS_TOKEN
    await hass.async_block_till_done()


async def test_tokens_that_dont_work(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(USER_URL, status=401)
    aioclient_mock.post(REFRESH_URL, status=400)

    result = await submit(hass, FORM)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_matkahuolto_cannot_be_reached(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(USER_URL, status=500)

    result = await submit(hass, FORM)

    assert result["errors"] == {"base": "cannot_connect"}


async def test_an_account_is_added_only_once(hass: HomeAssistant, matkahuolto: AiohttpClientMocker) -> None:
    account(hass)

    result = await submit(hass, {**FORM, "username": USERNAME.upper()})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_new_tokens_when_the_old_ones_stop_working(hass: HomeAssistant, matkahuolto: AiohttpClientMocker) -> None:
    entry = account(hass, access_token="expired", refresh_token="expired")

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"access_token": ACCESS_TOKEN, "refresh_token": f'"{REFRESH_TOKEN}"'}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == ENTRY_DATA


async def test_changing_the_settings(hass: HomeAssistant, matkahuolto: AiohttpClientMocker) -> None:
    entry = account(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "access_token": ACCESS_TOKEN,
            "refresh_token": REFRESH_TOKEN,
            "language": "en",
            "prioritize_undelivered": False,
            "max_shipments": 10.0,
            "stale_shipment_day_limit": 30.0,
            "completed_shipment_day_shown": 1.0,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {
        **ENTRY_DATA,
        "language": "en",
        "prioritize_undelivered": False,
        "max_shipments": 10,
        "stale_shipment_day_limit": 30,
        "completed_shipment_day_shown": 1,
    }
