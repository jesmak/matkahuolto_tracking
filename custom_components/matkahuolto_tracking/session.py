import logging
from typing import Optional

import requests
from requests import ConnectTimeout, RequestException

from .const import WWW_SERVICE_BASE_URL, USER_AGENT

_LOGGER = logging.getLogger(__name__)


class MatkahuoltoException(Exception):
    """Base exception for Matkahuolto"""


class MatkahuoltoSession:
    _access_token: str
    _refresh_token: str
    _language: str
    _timeout: int

    def __init__(self, access_token: str, refresh_token: str, language: str, timeout=20):
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._timeout = timeout
        self._language = language

    def _try_refresh_token(self) -> bool:
        try:
            response = requests.post(
                url=WWW_SERVICE_BASE_URL + "/user/token/refresh",
                json={"accessToken": self._access_token},
                headers={
                    "Authorization": self._refresh_token,
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/json"
                },
                timeout=self._timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                if "AuthenticationResult" in data:
                    auth_result = data["AuthenticationResult"]
                    if "AccessToken" in auth_result:
                        self._access_token = auth_result["AccessToken"]
                        _LOGGER.info("Token refresh successful")
                        return True
            else:
                _LOGGER.debug(
                    f"Token refresh failed [{response.status_code}]: "
                    f"{response.text[:200]}"
                )
                
        except Exception as e:
            _LOGGER.debug(f"Token refresh error: {e}")
        
        _LOGGER.warning(
            "Could not refresh access token. Please reconfigure the integration "
            "with new tokens from matkahuolto.fi"
        )
        return False

    def call_api(self, path: str, reauthenticated=False) -> Optional[dict]:
        try:
            response = requests.get(
                url=WWW_SERVICE_BASE_URL + path + "?language=" + self._language,
                headers={
                    "Authorization": self._access_token,
                    "User-Agent": USER_AGENT
                },
                timeout=self._timeout
            )

            if response.status_code == 401 and reauthenticated is False:
                if self._try_refresh_token():
                    return self.call_api(path, reauthenticated=True)
                else:
                    raise MatkahuoltoException("Access token expired. Refresh failed. Please provide new tokens.")

            elif response.status_code != 200:
                raise MatkahuoltoException(f"{response.status_code} is not valid")

            else:
                result = response.json() if response else {}
                return result

        except ConnectTimeout as exception:
            raise MatkahuoltoException("Timeout error") from exception

        except RequestException as exception:
            raise MatkahuoltoException(f"Communication error {exception}") from exception
