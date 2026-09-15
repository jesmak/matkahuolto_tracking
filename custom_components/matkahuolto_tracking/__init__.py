"""Matkahuolto package tracking: the coming and recently delivered packages of a matkahuolto.fi account.

Each config entry is one account, with a sensor that lists its packages in the
format package-tracker-card shows.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import CONF_USERNAME, DOMAIN
from .coordinator import MatkahuoltoConfigEntry, MatkahuoltoCoordinator

PLATFORMS = [Platform.SENSOR]

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
    """Gives entries of 1.x versions with tokens a unique id: the account's email address.

    Entries from before tokens, with a password, can't be migrated: the account has to be added again.
    """
    if entry.version != 2:
        return False
    if entry.minor_version < 2:
        hass.config_entries.async_update_entry(
            entry, unique_id=entry.data[CONF_USERNAME].strip().lower(), minor_version=2
        )
    return True
