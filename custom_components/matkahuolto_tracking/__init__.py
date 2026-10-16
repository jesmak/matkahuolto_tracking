"""Matkahuolto package tracking: the coming and recently delivered packages of a matkahuolto.fi account.

Each config entry is one account, with a sensor that lists its packages in the
format package-tracker-card shows.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_INCLUDE_PICKUP_DETAILS,
    CONF_MAX_OUTGOING_SHIPMENTS,
    CONF_MAX_SHIPMENTS,
    CONF_PICKUP_CODE,
    CONF_REFRESH_TOKEN,
    CONF_USERNAME,
    DEFAULT_MAX_SHIPMENTS,
    DOMAIN,
    PICKUP_CODE_CODE,
    PICKUP_CODE_NONE,
)
from .coordinator import MatkahuoltoConfigEntry, MatkahuoltoCoordinator

PLATFORMS = [Platform.EVENT, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: MatkahuoltoConfigEntry) -> bool:
    coordinator = MatkahuoltoCoordinator(hass, entry)
    # Tokens that no longer work start reauthentication; Matkahuolto being down retries the setup later.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MatkahuoltoConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: MatkahuoltoConfigEntry) -> bool:
    """Brings entries of earlier versions up to date.

    Version 1 entries have an email address and password but no tokens. They get empty tokens, which
    the first update finds refused, so it logs in with the password. Entries of 2.1 get a unique id, the
    account's email address, the pickup switch of 2.2 entries becomes a choice, and 2.3 entries get a maximum for sent
    packages.
    """
    if entry.version > 2:
        return False
    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry,
            data={CONF_ACCESS_TOKEN: "", CONF_REFRESH_TOKEN: "", **entry.data},
            version=2,
            minor_version=1,
        )
    if entry.minor_version < 2:
        hass.config_entries.async_update_entry(entry, unique_id=entry.data[CONF_USERNAME].strip().lower(), minor_version=2)
    if entry.minor_version < 3:
        # The pickup point is now always included, and the switch that held it back with the code became a choice.
        data = {key: value for key, value in entry.data.items() if key != CONF_INCLUDE_PICKUP_DETAILS}
        data[CONF_PICKUP_CODE] = PICKUP_CODE_CODE if entry.data.get(CONF_INCLUDE_PICKUP_DETAILS) else PICKUP_CODE_NONE
        # Entries from the token era took the email as typed, spaces and all, and logging in again uses it as it is. The
        # entities' unique ids are built from it, so they move with it, or they would be left behind for new ones.
        typed = str(data[CONF_USERNAME])
        data[CONF_USERNAME] = typed.strip()
        if typed != data[CONF_USERNAME]:
            old, new = f"matkahuolto_{typed}", f"matkahuolto_{data[CONF_USERNAME]}"

            @callback
            def moved(entity: er.RegistryEntry) -> dict[str, str] | None:
                if entity.unique_id == old or entity.unique_id.startswith(f"{old}_"):
                    return {"new_unique_id": new + entity.unique_id[len(old) :]}
                return None

            await er.async_migrate_entries(hass, entry.entry_id, moved)
        hass.config_entries.async_update_entry(entry, data=data, minor_version=3)
    if entry.minor_version < 4:
        # The one maximum was for received packages, and there were no others. Sent ones get the same.
        data = {**entry.data, CONF_MAX_OUTGOING_SHIPMENTS: entry.data.get(CONF_MAX_SHIPMENTS, DEFAULT_MAX_SHIPMENTS)}
        hass.config_entries.async_update_entry(entry, data=data, minor_version=4)
    return True
