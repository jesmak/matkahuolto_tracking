import logging
from typing import Optional

import requests
from requests import ConnectTimeout, RequestException

from .const import WWW_SERVICE_BASE_URL, USER_AGENT

_LOGGER = logging.getLogger(__name__)


class MatkahuoltoException(Exception):
    """Base exception for Matkahuolto"""


class MatkahuoltoSession:
    _username: str
    _password: str
    _language: str
    _timeout: int
    _tokens: any

    def __init__(self, username: str, password: str, language: str, timeout=20):
        self._username = username
        self._password = password
        self._timeout = timeout
        self._language = language

    def authenticate(self) -> None:
        try:
            session = requests.Session()

            response = session.post(
                url=f"{WWW_SERVICE_BASE_URL}/user/auth",
                headers={
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/json"
                },
                timeout=self._timeout,
                data=f"{{\"username\":\"{self._username}\",\"password\":\"{self._password}\"}}"
            )

            if response.status_code != 200:
                raise MatkahuoltoException(f"{response.status_code} is not valid")

            self._tokens = response.json()["AuthenticationResult"]

        except ConnectTimeout as exception:
            raise MatkahuoltoException("Timeout error") from exception

        except RequestException as exception:
            raise MatkahuoltoException(f"Communication error {exception}") from exception

    def call_api(self, path: str, reauthenticated=False) -> Optional[dict]:
        try:
            response = requests.get(
                url=WWW_SERVICE_BASE_URL + path + self._language,
                headers={
                    "Authorization": self._tokens['AccessToken']
                },
                timeout=self._timeout
            )

            if response.status_code == 401 and reauthenticated is False:
                self.authenticate()
                return self.call_api(path, True)  # avoid reauthentication loops by using the reauthenticated flag

            elif response.status_code != 200:
                raise MatkahuoltoException(f"{response.status_code} is not valid")

            else:
                result = response.json() if response else {}
                return result

        except ConnectTimeout as exception:
            raise MatkahuoltoException("Timeout error") from exception

        except RequestException as exception:
            raise MatkahuoltoException(f"Communication error {exception}") from exception
