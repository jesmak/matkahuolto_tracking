"""Config flow: an account is added by logging in with its email address and password, then choosing settings.

The login is made the way the Matkahuolto Paketit app makes it, which needs no reCAPTCHA. The password
is kept, so that the integration can log in again when the refresh token stops working; only when
the password itself is refused does reauthentication ask for it. Reconfiguring offers a choice:
change the settings, or log in again (with a new password or email address, for example). Logging in
again is checked to be the same account by its id in Matkahuolto's login service, as its email can change.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
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

from .api import MatkahuoltoAuthError, MatkahuoltoClient, MatkahuoltoError, MatkahuoltoLoginRejectedError, log_in, subject_of
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_COMPLETED_SHIPMENT_DAYS_SHOWN,
    CONF_EMAIL,
    CONF_LANGUAGE,
    CONF_MAX_SHIPMENTS,
    CONF_PASSWORD,
    CONF_PICKUP_CODE,
    CONF_PRIORITIZE_UNDELIVERED,
    CONF_REFRESH_TOKEN,
    CONF_STALE_SHIPMENT_DAY_LIMIT,
    CONF_SUBJECT,
    CONF_USERNAME,
    DEFAULT_COMPLETED_SHIPMENT_DAYS_SHOWN,
    DEFAULT_MAX_SHIPMENTS,
    DEFAULT_PICKUP_CODE,
    DEFAULT_PRIORITIZE_UNDELIVERED,
    DEFAULT_STALE_SHIPMENT_DAY_LIMIT,
    DOMAIN,
    LANGUAGES,
    PICKUP_CODE_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)

LOGIN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")),
        vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")),
    }
)

DAYS_SELECTOR = NumberSelector(NumberSelectorConfig(min=0, max=365, step=1, mode=NumberSelectorMode.BOX))
SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LANGUAGE): SelectSelector(
            SelectSelectorConfig(options=LANGUAGES, translation_key=CONF_LANGUAGE, mode=SelectSelectorMode.DROPDOWN)
        ),
        vol.Required(CONF_PRIORITIZE_UNDELIVERED): BooleanSelector(),
        vol.Required(CONF_MAX_SHIPMENTS): NumberSelector(NumberSelectorConfig(min=1, max=50, step=1, mode=NumberSelectorMode.BOX)),
        vol.Required(CONF_STALE_SHIPMENT_DAY_LIMIT): DAYS_SELECTOR,
        vol.Required(CONF_COMPLETED_SHIPMENT_DAYS_SHOWN): DAYS_SELECTOR,
        vol.Required(CONF_PICKUP_CODE): SelectSelector(
            SelectSelectorConfig(options=PICKUP_CODE_OPTIONS, translation_key=CONF_PICKUP_CODE, mode=SelectSelectorMode.DROPDOWN)
        ),
    }
)


def clean_settings(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Submitted settings, normalised for storing."""
    data = dict(user_input)
    for key in (CONF_MAX_SHIPMENTS, CONF_STALE_SHIPMENT_DAY_LIMIT, CONF_COMPLETED_SHIPMENT_DAYS_SHOWN):
        if key in data:
            data[key] = int(data[key])
    return data


def login_email(entry: ConfigEntry) -> str:
    """The email address the account logs in with: a newer one when it has changed, else the one it was added with."""
    return entry.data.get(CONF_EMAIL) or entry.data[CONF_USERNAME]


def same_account(entry: ConfigEntry, email: str, subject: str | None) -> bool:
    """Whether a login is of the account an entry follows: by its id when both have one, as an email can change, and
    by the email it logs in with otherwise."""
    saved = entry.data.get(CONF_SUBJECT)
    if saved and subject:
        return subject == saved
    return email.strip().lower() == login_email(entry).strip().lower()


class MatkahuoltoConfigFlow(ConfigFlow, domain=DOMAIN):
    # 1.x entries have no tokens, 2.1 entries no unique id, and 2.2 entries the old pickup switch.
    # __init__.async_migrate_entry updates them all.
    VERSION = 2
    MINOR_VERSION = 3

    def __init__(self) -> None:
        # The logged-in account (email, password and tokens), between the login and settings steps.
        self._account: dict[str, str] = {}

    async def _log_in(self, username: str, password: str, language: str) -> dict[str, str]:
        """Logs in and checks the tokens by reading the account. Returns the errors.

        On success, the account's email address, password, tokens and id are in self._account.
        """
        session = async_get_clientsession(self.hass)
        try:
            access_token, refresh_token = await log_in(session, username, password)
            await MatkahuoltoClient(session, access_token, refresh_token, language).user()
        except MatkahuoltoAuthError as err:
            _LOGGER.warning("Matkahuolto didn't accept the login: %s", err)
            return {"base": "invalid_auth"}
        except MatkahuoltoLoginRejectedError as err:
            _LOGGER.warning("Matkahuolto turned the login away: %s", err)
            return {"base": "login_rejected"}
        except MatkahuoltoError as err:
            _LOGGER.warning("Logging in to Matkahuolto failed: %s", err)
            return {"base": "cannot_connect"}
        self._account = {
            CONF_USERNAME: username,
            CONF_PASSWORD: password,
            CONF_ACCESS_TOKEN: access_token,
            CONF_REFRESH_TOKEN: refresh_token,
        }
        if subject := subject_of(access_token):
            self._account[CONF_SUBJECT] = subject
        return {}

    def _language(self) -> str:
        language = self.hass.config.language[:2]
        return language if language in LANGUAGES else "en"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Logging in."""
        errors: dict[str, str] = {}
        if user_input is not None:
            username = str(user_input[CONF_USERNAME]).strip()
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()
            errors = await self._log_in(username, user_input[CONF_PASSWORD], self._language())
            if not errors:
                return await self.async_step_settings()

        suggested = {CONF_USERNAME: user_input[CONF_USERNAME]} if user_input else {}
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(LOGIN_SCHEMA, suggested),
            errors=errors,
        )

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The settings of a newly logged-in account."""
        username = self._account[CONF_USERNAME]
        if user_input is not None:
            return self.async_create_entry(title=username, data={**self._account, **clean_settings(user_input)})

        defaults = {
            CONF_LANGUAGE: self._language(),
            CONF_PRIORITIZE_UNDELIVERED: DEFAULT_PRIORITIZE_UNDELIVERED,
            CONF_MAX_SHIPMENTS: DEFAULT_MAX_SHIPMENTS,
            CONF_STALE_SHIPMENT_DAY_LIMIT: DEFAULT_STALE_SHIPMENT_DAY_LIMIT,
            CONF_COMPLETED_SHIPMENT_DAYS_SHOWN: DEFAULT_COMPLETED_SHIPMENT_DAYS_SHOWN,
            CONF_PICKUP_CODE: DEFAULT_PICKUP_CODE,
        }
        return self.async_show_form(
            step_id="settings",
            data_schema=self.add_suggested_values_to_schema(SETTINGS_SCHEMA, defaults),
            description_placeholders={"username": username},
        )

    async def _log_in_again(self, entry: ConfigEntry, user_input: dict[str, Any]) -> dict[str, str]:
        """Logging in again to the account of an entry, with the email address it now has. Returns the errors."""
        email = str(user_input[CONF_USERNAME]).strip()
        errors = await self._log_in(email, user_input[CONF_PASSWORD], entry.data[CONF_LANGUAGE])
        if not errors and not same_account(entry, email, self._account.get(CONF_SUBJECT)):
            errors = {"base": "wrong_account"}
        return errors

    def _login_data(self) -> dict[str, str]:
        """The new login: the password, tokens and id, and the email address it was made with. An entry keeps its
        username, which its entities' ids are built from."""
        data = {key: value for key, value in self._account.items() if key != CONF_USERNAME}
        data[CONF_EMAIL] = self._account[CONF_USERNAME]
        return data

    def _show_login_again(
        self, step_id: str, entry: ConfigEntry, errors: dict[str, str], user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        email = user_input[CONF_USERNAME] if user_input else login_email(entry)
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(LOGIN_SCHEMA, {CONF_USERNAME: email}),
            errors=errors,
            description_placeholders={"username": login_email(entry)},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The password, when Matkahuolto no longer accepts the saved login."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._log_in_again(entry, user_input)
            if not errors:
                data = {**entry.data, **self._login_data()}
                return self.async_update_reload_and_abort(entry, title=data[CONF_EMAIL], data=data)
        return self._show_login_again("reauth_confirm", entry, errors, user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Changing the settings, or logging in again."""
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=["reconfigure_settings", "reconfigure_login"],
            description_placeholders={"username": login_email(self._get_reconfigure_entry())},
        )

    async def async_step_reconfigure_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return self.async_update_reload_and_abort(entry, data={**entry.data, **clean_settings(user_input)})
        return self.async_show_form(
            step_id="reconfigure_settings",
            data_schema=self.add_suggested_values_to_schema(SETTINGS_SCHEMA, dict(entry.data)),
            description_placeholders={"username": login_email(entry)},
        )

    async def async_step_reconfigure_login(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._log_in_again(entry, user_input)
            if not errors:
                data = {**entry.data, **self._login_data()}
                return self.async_update_reload_and_abort(entry, title=data[CONF_EMAIL], data=data)
        return self._show_login_again("reconfigure_login", entry, errors, user_input)
