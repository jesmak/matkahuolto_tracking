"""Matkahuolto's web service: the account and the packages sent to it.

Requests carry the access token of a login to matkahuolto.fi. When it has
expired, the refresh token gets a new one. When that fails too, the account logs
in again with its email address and password, the way the Matkahuolto Paketit
app does. Only when that is refused is the user asked for the password again.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    LOGIN_USER_AGENT,
    PAKETIT_CLIENT,
    PATH_AUTH,
    PATH_RECEIVED_SHIPMENTS,
    PATH_REFRESH_TOKEN,
    PATH_USER,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=20)


class MatkahuoltoError(Exception):
    """Matkahuolto couldn't be reached, or it answered with an error."""


class MatkahuoltoAuthError(MatkahuoltoError):
    """The login doesn't work: a wrong password, or tokens that stopped working with no password to log in again."""


class MatkahuoltoLoginRejectedError(MatkahuoltoError):
    """Matkahuolto turned the login away without looking at the password: it no longer takes it as the app's."""


def _tokens(body: Any) -> tuple[str | None, str | None]:
    """The access and refresh token of a Cognito AuthenticationResult."""
    result = body.get("AuthenticationResult") if isinstance(body, dict) else None
    if not isinstance(result, dict):
        return None, None
    access_token, refresh_token = result.get("AccessToken"), result.get("RefreshToken")
    return (
        access_token if isinstance(access_token, str) and access_token else None,
        refresh_token if isinstance(refresh_token, str) and refresh_token else None,
    )


async def log_in(session: aiohttp.ClientSession, username: str, password: str) -> tuple[str, str]:
    """Logs in with an email address and password. Returns the access and refresh token."""
    try:
        async with session.post(
            API_BASE_URL + PATH_AUTH,
            json={"username": username, "password": password},
            headers={
                "Accept": "application/json, text/plain, */*",
                "Paketit-Client": PAKETIT_CLIENT,
                "User-Agent": LOGIN_USER_AGENT,
            },
            timeout=TIMEOUT,
        ) as response:
            status = response.status
            body = await response.json(content_type=None) if status == 200 else await response.text()
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise MatkahuoltoError(f"Matkahuolto couldn't be reached for logging in: {err}") from err

    if status in (401, 403):
        raise MatkahuoltoAuthError("Matkahuolto didn't accept the email address and password")
    if status == 400:
        raise MatkahuoltoLoginRejectedError(f"Matkahuolto turned the login away: {str(body)[:100]}")
    if status != 200:
        raise MatkahuoltoError(f"Matkahuolto couldn't log in (status {status})")
    access_token, refresh_token = _tokens(body)
    if access_token is None or refresh_token is None:
        raise MatkahuoltoError("Matkahuolto's login answer had no tokens")
    return access_token, refresh_token


class MatkahuoltoClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str,
        refresh_token: str,
        language: str,
        on_new_tokens: Callable[[str, str], None] | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._language = language
        # Called with new access and refresh tokens, so that they can be saved for the next start.
        self._on_new_tokens = on_new_tokens
        # For logging in again when the refresh token stops working. Entries from before
        # password logins have none, and are asked for it.
        self._username = username
        self._password = password

    @property
    def access_token(self) -> str:
        return self._access_token

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    async def user(self) -> Any:
        """The account. Used for checking the tokens."""
        return await self._get(PATH_USER)

    async def received_shipments(self) -> list[dict[str, Any]]:
        data = await self._get(PATH_RECEIVED_SHIPMENTS)
        shipments = data.get("shipments") if isinstance(data, dict) else None
        if not isinstance(shipments, list):
            raise MatkahuoltoError("Matkahuolto sent the shipments in an unexpected format")
        return [shipment for shipment in shipments if isinstance(shipment, dict)]

    async def _get(self, path: str) -> Any:
        status, body = await self._fetch(path)
        if status == 401:
            await self._renew_tokens()
            status, body = await self._fetch(path)
            if status == 401:
                raise MatkahuoltoAuthError("Matkahuolto refused the refreshed access token")
        if status != 200:
            raise MatkahuoltoError(f"Matkahuolto answered with status {status}")
        return body

    async def _fetch(self, path: str) -> tuple[int, Any]:
        try:
            async with self._session.get(
                API_BASE_URL + path,
                params={"language": self._language},
                headers={"Authorization": self._access_token, "User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            ) as response:
                if response.status != 200:
                    return response.status, None
                return response.status, await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise MatkahuoltoError(f"Matkahuolto couldn't be reached: {err}") from err

    async def _renew_tokens(self) -> None:
        """A new access token from the refresh token; when that is refused, a new login."""
        try:
            await self._refresh_access_token()
        except MatkahuoltoAuthError:
            if not (self._username and self._password):
                raise
            _LOGGER.debug("The refresh token was refused, logging in again")
            self._access_token, self._refresh_token = await log_in(self._session, self._username, self._password)
            self._tokens_changed()

    def _tokens_changed(self) -> None:
        if self._on_new_tokens is not None:
            self._on_new_tokens(self._access_token, self._refresh_token)

    async def _refresh_access_token(self) -> None:
        try:
            async with self._session.post(
                API_BASE_URL + PATH_REFRESH_TOKEN,
                json={"accessToken": self._access_token},
                headers={"Authorization": self._refresh_token, "User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            ) as response:
                status = response.status
                body = await response.json(content_type=None) if status == 200 else None
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise MatkahuoltoError(f"Matkahuolto couldn't be reached for a new access token: {err}") from err

        # A server error says nothing about the tokens: try again at the next update.
        if status >= 500:
            raise MatkahuoltoError(f"Matkahuolto couldn't refresh the access token (status {status})")
        access_token, _refresh_token = _tokens(body)
        if access_token is None:
            raise MatkahuoltoAuthError("Matkahuolto didn't give a new access token")

        self._access_token = access_token
        _LOGGER.debug("Refreshed the access token")
        self._tokens_changed()
