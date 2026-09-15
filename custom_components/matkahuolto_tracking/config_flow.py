"""Config flow: an account is added with the tokens of a login to matkahuolto.fi.

The tokens are copied from the browser; the README shows how. The coordinator
saves a refreshed access token, and when the refresh token stops working too,
reauthentication asks for new tokens. Settings are changed by reconfiguring.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import MatkahuoltoAuthError, MatkahuoltoClient, MatkahuoltoError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_COMPLETED_SHIPMENT_DAYS_SHOWN,
    CONF_LANGUAGE,
    CONF_MAX_SHIPMENTS,
    CONF_PRIORITIZE_UNDELIVERED,
    CONF_REFRESH_TOKEN,
    CONF_STALE_SHIPMENT_DAY_LIMIT,
    CONF_USERNAME,
    DEFAULT_COMPLETED_SHIPMENT_DAYS_SHOWN,
    DEFAULT_MAX_SHIPMENTS,
    DEFAULT_PRIORITIZE_UNDELIVERED,
    DEFAULT_STALE_SHIPMENT_DAY_LIMIT,
    DOMAIN,
    LANGUAGES,
)

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
DAYS_SELECTOR = NumberSelector(NumberSelectorConfig(min=0, max=365, step=1, mode=NumberSelectorMode.BOX))

TOKEN_FIELDS = {
    vol.Required(CONF_ACCESS_TOKEN): TOKEN_SELECTOR,
    vol.Required(CONF_REFRESH_TOKEN): TOKEN_SELECTOR,
}
SETTING_FIELDS = {
    vol.Required(CONF_LANGUAGE): SelectSelector(
        SelectSelectorConfig(options=LANGUAGES, translation_key=CONF_LANGUAGE, mode=SelectSelectorMode.DROPDOWN)
    ),
    vol.Required(CONF_PRIORITIZE_UNDELIVERED): BooleanSelector(),
    vol.Required(CONF_MAX_SHIPMENTS): NumberSelector(
        NumberSelectorConfig(min=1, max=50, step=1, mode=NumberSelectorMode.BOX)
    ),
    vol.Required(CONF_STALE_SHIPMENT_DAY_LIMIT): DAYS_SELECTOR,
    vol.Required(CONF_COMPLETED_SHIPMENT_DAYS_SHOWN): DAYS_SELECTOR,
}

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        **TOKEN_FIELDS,
        **SETTING_FIELDS,
    }
)
RECONFIGURE_SCHEMA = vol.Schema({**TOKEN_FIELDS, **SETTING_FIELDS})
REAUTH_SCHEMA = vol.Schema(TOKEN_FIELDS)


def clean_token(value: Any) -> str:
    """A token as copied from the browser, without surrounding spaces or quotation marks."""
    return str(value or "").strip().strip('"').strip()


def clean_input(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Submitted values, normalised for storing."""
    data = dict(user_input)
    if CONF_USERNAME in data:
        data[CONF_USERNAME] = str(data[CONF_USERNAME]).strip()
    for key in (CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN):
        if key in data:
            data[key] = clean_token(data[key])
    for key in (CONF_MAX_SHIPMENTS, CONF_STALE_SHIPMENT_DAY_LIMIT, CONF_COMPLETED_SHIPMENT_DAYS_SHOWN):
        if key in data:
            data[key] = int(data[key])
    return data


async def check_tokens(hass: HomeAssistant, data: Mapping[str, Any]) -> tuple[dict[str, str], str]:
    """Tries the tokens. Returns the errors, and the access token, refreshed if it had expired."""
    client = MatkahuoltoClient(
        async_get_clientsession(hass), data[CONF_ACCESS_TOKEN], data[CONF_REFRESH_TOKEN], data[CONF_LANGUAGE]
    )
    try:
        await client.user()
    except MatkahuoltoAuthError:
        return {"base": "invalid_auth"}, data[CONF_ACCESS_TOKEN]
    except MatkahuoltoError:
        return {"base": "cannot_connect"}, data[CONF_ACCESS_TOKEN]
    return {}, client.access_token


class MatkahuoltoConfigFlow(ConfigFlow, domain=DOMAIN):
    # 2.1 entries have no unique id; __init__.async_migrate_entry gives them one.
    VERSION = 2
    MINOR_VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = clean_input(user_input)
            await self.async_set_unique_id(data[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()
            errors, access_token = await check_tokens(self.hass, data)
            if not errors:
                return self.async_create_entry(
                    title=data[CONF_USERNAME], data={**data, CONF_ACCESS_TOKEN: access_token}
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input or self._defaults()),
            errors=errors,
        )

    def _defaults(self) -> dict[str, Any]:
        language = self.hass.config.language[:2]
        return {
            CONF_LANGUAGE: language if language in LANGUAGES else "en",
            CONF_PRIORITIZE_UNDELIVERED: DEFAULT_PRIORITIZE_UNDELIVERED,
            CONF_MAX_SHIPMENTS: DEFAULT_MAX_SHIPMENTS,
            CONF_STALE_SHIPMENT_DAY_LIMIT: DEFAULT_STALE_SHIPMENT_DAY_LIMIT,
            CONF_COMPLETED_SHIPMENT_DAYS_SHOWN: DEFAULT_COMPLETED_SHIPMENT_DAYS_SHOWN,
        }

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """New tokens, when Matkahuolto no longer accepts the saved ones."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **clean_input(user_input)}
            errors, access_token = await check_tokens(self.hass, data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data={**data, CONF_ACCESS_TOKEN: access_token})

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"username": entry.data[CONF_USERNAME]},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Changing the tokens or settings of an account."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **clean_input(user_input)}
            errors, access_token = await check_tokens(self.hass, data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data={**data, CONF_ACCESS_TOKEN: access_token})

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(RECONFIGURE_SCHEMA, user_input or dict(entry.data)),
            errors=errors,
            description_placeholders={"username": entry.data[CONF_USERNAME]},
        )
