"""The counts of an account's packages, and the events its packages fire."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse

from custom_components.matkahuolto_tracking.const import DOMAIN

from .conftest import ENTRY_DATA, NOW, SHIPMENTS_URL, USER_URL, USERNAME, shipment

EVENT_ENTITY = "event.matkahuolto_matti_meikalainen_example_com_package"
ON_THE_WAY = "sensor.matkahuolto_matti_meikalainen_example_com_packages_on_the_way"
READY = "sensor.matkahuolto_matti_meikalainen_example_com_packages_ready_for_pickup"


async def answer(shipments: list[dict[str, Any]]) -> AiohttpClientMockResponse:
    """Matkahuolto's answer, read afresh each time so a test can change the shipments."""
    return AiohttpClientMockResponse("get", SHIPMENTS_URL, json={"shipments": list(shipments)})


def account(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, title=USERNAME, version=2, minor_version=2, unique_id=USERNAME, data=ENTRY_DATA
    )
    entry.add_to_hass(hass)
    return entry


async def set_up(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> MockConfigEntry:
    freezer.move_to(NOW)
    entry = account(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def test_the_counts_of_the_packages(
    hass: HomeAssistant, matkahuolto: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    await set_up(hass, freezer)

    assert hass.states.get(ON_THE_WAY).state == "2", "ready for pickup and in transport"
    assert hass.states.get(ON_THE_WAY).attributes["state_class"] == "measurement"
    assert hass.states.get(READY).state == "1"
    registry = er.async_get(hass)
    assert registry.async_get(ON_THE_WAY).unique_id == f"matkahuolto_{USERNAME}_on_the_way"
    assert registry.async_get(READY).unique_id == f"matkahuolto_{USERNAME}_ready_for_pickup"


async def test_the_packages_already_there_are_not_events(
    hass: HomeAssistant, matkahuolto: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    await set_up(hass, freezer)

    state = hass.states.get(EVENT_ENTITY)
    assert state.state == "unknown", "what was already there when Home Assistant started has not just happened"
    assert set(state.attributes["event_types"]) == {"new_package", "moved", "ready_for_pickup", "delivered"}


async def test_a_package_becoming_ready_for_pickup_fires_an_event(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    moving = shipment("MH0100", 35, "2026-09-16T08:30:00", event="Lähetys on kuljetuksessa")
    arrived = shipment("MH0100", 55, "2026-09-16T11:30:00")
    shipments = [moving]
    aioclient_mock.get(USER_URL, json={"email": USERNAME})
    aioclient_mock.get(SHIPMENTS_URL, side_effect=lambda *_: answer(shipments))

    await set_up(hass, freezer)
    assert hass.states.get(EVENT_ENTITY).state == "unknown"

    shipments[:] = [arrived]
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(EVENT_ENTITY)
    assert state.attributes["event_type"] == "ready_for_pickup"
    assert state.attributes["shipment_number"] == "MH0100"
    assert state.attributes["source"] == "Matkahuolto"
    assert hass.states.get(READY).state == "1"


async def test_every_change_of_one_update_fires_its_own_event(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    before = [
        shipment("MH0201", 35, "2026-09-16T08:30:00", event="Lähetys on kuljetuksessa"),
        shipment("MH0202", 40, "2026-09-16T08:40:00", event="Lähetys on jakelussa"),
    ]
    after = [
        shipment("MH0201", 55, "2026-09-16T11:30:00"),
        shipment("MH0202", 62, "2026-09-16T11:31:00", event="Lähetys on toimitettu"),
    ]
    shipments = list(before)
    aioclient_mock.get(USER_URL, json={"email": USERNAME})
    aioclient_mock.get(SHIPMENTS_URL, side_effect=lambda *_: answer(shipments))
    await set_up(hass, freezer)

    seen: list[str] = []
    hass.bus.async_listen(
        "state_changed",
        lambda call: (
            seen.append(call.data["new_state"].attributes.get("event_type"))
            if call.data["entity_id"] == EVENT_ENTITY and call.data["new_state"]
            else None
        ),
    )

    shipments[:] = after
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert seen == ["ready_for_pickup", "delivered"], "one event for each package that changed"
