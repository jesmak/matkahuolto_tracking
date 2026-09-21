"""Setting up an account and its sensor, entries of earlier versions, and token problems."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.matkahuolto_tracking.const import DOMAIN
from custom_components.matkahuolto_tracking.sensor import MatkahuoltoSensor

from .conftest import (
    AUTH_URL,
    ENTRY_DATA,
    LOGIN,
    NEW_ACCESS_TOKEN,
    NEW_REFRESH_TOKEN,
    NOW,
    PASSWORD,
    REFRESH_URL,
    SHIPMENTS,
    SHIPMENTS_URL,
    USERNAME,
    answers,
)

ENTITY_ID = "sensor.matkahuolto_matti_meikalainen_example_com"


def account(hass: HomeAssistant, **options: object) -> MockConfigEntry:
    data = options.pop("data", None)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=USERNAME,
        version=options.pop("version", 2),
        minor_version=options.pop("minor_version", 2),
        unique_id=options.pop("unique_id", USERNAME),
        data=data if data is not None else {**ENTRY_DATA, **options},
    )
    entry.add_to_hass(hass)
    return entry


async def test_the_sensor_lists_the_packages(
    hass: HomeAssistant, matkahuolto: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(NOW)
    entry = account(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == "2026-09-16T05:30:00+00:00", "the latest change, from the shipment in transport"
    assert state.attributes["device_class"] == "timestamp"
    assert state.attributes["attribution"] == "Data provided by Oy Matkahuolto Ab"
    assert [package["shipment_number"] for package in state.attributes["packages"]] == [
        "MH0002",
        "MH0001",
        "MH0006",
        "MH0003",
    ]
    assert er.async_get(hass).async_get(ENTITY_ID).unique_id == f"matkahuolto_{USERNAME}", "as in earlier versions"

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_packages_are_kept_out_of_the_recorder() -> None:
    assert "packages" in MatkahuoltoSensor._unrecorded_attributes


async def test_an_entry_of_an_earlier_version_gets_a_unique_id(
    hass: HomeAssistant, matkahuolto: AiohttpClientMocker
) -> None:
    entry = account(hass, minor_version=1, unique_id=None, username="Matti.Meikalainen@example.com")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert (entry.minor_version, entry.unique_id) == (2, USERNAME)


async def test_a_refreshed_access_token_is_saved(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(NOW)
    aioclient_mock.get(SHIPMENTS_URL, side_effect=answers((401, None), (200, {"shipments": SHIPMENTS})))
    aioclient_mock.post(REFRESH_URL, json={"AuthenticationResult": {"AccessToken": NEW_ACCESS_TOKEN}})
    entry = account(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data["access_token"] == NEW_ACCESS_TOKEN
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(ENTITY_ID).state == "2026-09-16T05:30:00+00:00"


async def test_tokens_that_stop_working_log_in_again(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(NOW)
    aioclient_mock.get(SHIPMENTS_URL, side_effect=answers((401, None), (200, {"shipments": SHIPMENTS})))
    aioclient_mock.post(REFRESH_URL, status=401)
    aioclient_mock.post(AUTH_URL, json=LOGIN)
    entry = account(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert (entry.data["access_token"], entry.data["refresh_token"]) == (NEW_ACCESS_TOKEN, NEW_REFRESH_TOKEN)
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


async def test_a_password_that_stops_working_asks_for_a_new_one(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(SHIPMENTS_URL, status=401)
    aioclient_mock.post(REFRESH_URL, status=401)
    aioclient_mock.post(AUTH_URL, status=401)
    entry = account(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    [flow] = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == SOURCE_REAUTH


async def test_an_entry_without_a_password_asks_for_it(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(SHIPMENTS_URL, status=401)
    aioclient_mock.post(REFRESH_URL, status=401)
    entry = account(hass, data={key: value for key, value in ENTRY_DATA.items() if key != "password"})
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    [flow] = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == SOURCE_REAUTH


async def test_an_entry_from_before_tokens_logs_in_with_its_password(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(NOW)
    aioclient_mock.get(SHIPMENTS_URL, side_effect=answers((401, None), (200, {"shipments": SHIPMENTS})))
    aioclient_mock.post(REFRESH_URL, status=400)
    aioclient_mock.post(AUTH_URL, json=LOGIN)
    version_1 = {
        "username": "Matti.Meikalainen@example.com",
        "password": PASSWORD,
        "language": "fi",
        "prioritize_undelivered": True,
        "max_shipments": 5,
        "stale_shipment_day_limit": 15,
        "completed_shipment_day_shown": 3,
    }
    entry = account(hass, version=1, minor_version=1, unique_id=None, data=version_1)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert (entry.version, entry.minor_version, entry.unique_id) == (2, 2, USERNAME)
    assert (entry.data["access_token"], entry.data["refresh_token"]) == (NEW_ACCESS_TOKEN, NEW_REFRESH_TOKEN)
    assert hass.states.get(ENTITY_ID) is not None


async def test_the_sensor_is_unavailable_while_matkahuolto_is_down(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(NOW)
    aioclient_mock.get(SHIPMENTS_URL, side_effect=answers((200, {"shipments": SHIPMENTS}), (503, None)))
    entry = account(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state != STATE_UNAVAILABLE

    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
