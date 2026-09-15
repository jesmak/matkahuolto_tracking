"""Matkahuolto's web service: the account and the packages sent to it.

Requests carry the access token of a login to matkahuolto.fi. When it has
expired, the refresh token gets a new one. When that fails too, new tokens are
needed from the browser.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import aiohttp

from .const import API_BASE_URL, PATH_RECEIVED_SHIPMENTS, PATH_REFRESH_TOKEN, PATH_USER, USER_AGENT

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=20)


class MatkahuoltoError(Exception):
    """Matkahuolto couldn't be reached, or it answered with an error."""


class MatkahuoltoAuthError(MatkahuoltoError):
    """The tokens don't work any more, and new ones are needed."""


class MatkahuoltoClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str,
        refresh_token: str,
        language: str,
        on_new_access_token: Callable[[str], None] | None = None,
    ) -> None:
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._language = language
        # Called with a refreshed access token, so that it can be saved for the next start.
        self._on_new_access_token = on_new_access_token

    @property
    def access_token(self) -> str:
        return self._access_token

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
            await self._refresh_access_token()
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
        result = body.get("AuthenticationResult") if isinstance(body, dict) else None
        access_token = result.get("AccessToken") if isinstance(result, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise MatkahuoltoAuthError("Matkahuolto didn't give a new access token")

        self._access_token = access_token
        _LOGGER.debug("Refreshed the access token")
        if self._on_new_access_token is not None:
            self._on_new_access_token(access_token)
