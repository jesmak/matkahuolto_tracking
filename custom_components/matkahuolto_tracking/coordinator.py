"""Fetching the packages of an account every 10 minutes."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import MatkahuoltoAuthError, MatkahuoltoClient, MatkahuoltoError, MatkahuoltoPasswordRefusedError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EMAIL,
    CONF_LANGUAGE,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_USERNAME,
    DOMAIN,
    UPDATE_INTERVAL,
)
from .shipments import Packages, PackageSettings, build_packages

_LOGGER = logging.getLogger(__name__)

type MatkahuoltoConfigEntry = ConfigEntry[MatkahuoltoCoordinator]


class MatkahuoltoCoordinator(DataUpdateCoordinator[Packages]):
    config_entry: MatkahuoltoConfigEntry

    def __init__(self, hass: HomeAssistant, entry: MatkahuoltoConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            # Not the title, which is the account's email, so the integration's own update errors don't name the account
            # in logs that end up in bug reports. Home Assistant still logs the title itself when setting up.
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.settings = PackageSettings.from_data(entry.data)
        self.client = MatkahuoltoClient(
            async_get_clientsession(hass),
            entry.data[CONF_ACCESS_TOKEN],
            entry.data[CONF_REFRESH_TOKEN],
            entry.data[CONF_LANGUAGE],
            self._save_tokens,
            entry.data.get(CONF_EMAIL) or entry.data[CONF_USERNAME],
            entry.data.get(CONF_PASSWORD),
        )

    @callback
    def _save_tokens(self, access_token: str, refresh_token: str) -> None:
        """Keeps refreshed tokens, or those of a new login, so the next start doesn't begin with spent ones.

        The entry has no update listener, so saving the tokens doesn't reload the integration.
        """
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_ACCESS_TOKEN: access_token, CONF_REFRESH_TOKEN: refresh_token},
        )

    @property
    def device_info(self) -> DeviceInfo:
        """The account as a device, which all of its entities belong to."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            translation_key="account",
            translation_placeholders={"username": self.config_entry.data[CONF_USERNAME]},
            manufacturer="Matkahuolto",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def _async_update_data(self) -> Packages:
        try:
            shipments = await self.client.received_shipments()
        except MatkahuoltoPasswordRefusedError as err:
            # Dropped, so that no restart tries it again before the user gives the new one.
            data = {key: value for key, value in self.config_entry.data.items() if key != CONF_PASSWORD}
            self.hass.config_entries.async_update_entry(self.config_entry, data=data)
            raise ConfigEntryAuthFailed(str(err)) from err
        except MatkahuoltoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MatkahuoltoError as err:
            raise UpdateFailed(str(err)) from err
        return build_packages(shipments, self.settings, dt_util.now())
