"""Fetching the packages of an account every 10 minutes."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import MatkahuoltoAuthError, MatkahuoltoClient, MatkahuoltoError
from .const import CONF_ACCESS_TOKEN, CONF_LANGUAGE, CONF_REFRESH_TOKEN, DOMAIN, UPDATE_INTERVAL
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
            name=f"{DOMAIN} {entry.title}",
            update_interval=UPDATE_INTERVAL,
        )
        self.settings = PackageSettings.from_data(entry.data)
        self.client = MatkahuoltoClient(
            async_get_clientsession(hass),
            entry.data[CONF_ACCESS_TOKEN],
            entry.data[CONF_REFRESH_TOKEN],
            entry.data[CONF_LANGUAGE],
            self._save_access_token,
        )

    @callback
    def _save_access_token(self, access_token: str) -> None:
        """Keeps a refreshed access token, so that the next start doesn't begin with an expired one.

        The entry has no update listener, so saving the token doesn't reload the integration.
        """
        self.hass.config_entries.async_update_entry(
            self.config_entry, data={**self.config_entry.data, CONF_ACCESS_TOKEN: access_token}
        )

    async def _async_update_data(self) -> Packages:
        try:
            shipments = await self.client.received_shipments()
        except MatkahuoltoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MatkahuoltoError as err:
            raise UpdateFailed(str(err)) from err
        return build_packages(shipments, self.settings, dt_util.now())
