#!/usr/bin/env python3
"""mhlogin.py — Matkahuolto login helper. Prints the tokens the integration needs.

Standard library only, no install. Works on Linux, Windows and macOS.

    python3 mhlogin.py

It asks for your matkahuolto.fi email and password and signs in the way the Matkahuolto Paketit
app does — the app's login endpoint takes just email and password (no reCAPTCHA, unlike the
website), so this needs no browser and no developer tools. It prints an access token and a refresh
token to paste into the integration's setup.

Your password is only sent to matkahuolto.fi to log in; it is not stored anywhere.
"""

import getpass
import json
import urllib.error
import urllib.request

AUTH_URL = "https://wwwservice.matkahuolto.fi/user/auth"
# The header the Paketit app sends to identify itself; without it the endpoint wants a reCAPTCHA.
# If login ever starts failing, bump this to the current app version (android/<versionName>.<code>).
PAKETIT_CLIENT = "android/1.64.1291"
# The app's HTTP client. The endpoint turns away browser, curl and Python user agents with
# "400 Invalid request" before checking the password (seen 21 Sep 2026).
USER_AGENT = "okhttp/4.12.0"


def main() -> None:
    email = input("matkahuolto.fi email: ").strip()
    password = getpass.getpass("matkahuolto.fi password: ")

    body = json.dumps({"username": email, "password": password}).encode()
    req = urllib.request.Request(
        AUTH_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Paketit-Client": PAKETIT_CLIENT,
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:300]
        print(f"\nLogin failed ({err.code}). {detail}")
        print("Check the email and password. If it keeps failing, the app version header may be out of date.")
        return
    except (urllib.error.URLError, TimeoutError, ValueError) as err:
        print(f"\nCould not reach matkahuolto.fi: {err}")
        return

    result = payload.get("AuthenticationResult") if isinstance(payload, dict) else None
    if not isinstance(result, dict) or not result.get("AccessToken"):
        print("\nUnexpected response from matkahuolto.fi:", payload)
        return

    print("\nPaste these into the integration's setup:\n")
    print("Access token:")
    print(result["AccessToken"])
    print("\nRefresh token:")
    print(result["RefreshToken"])


if __name__ == "__main__":
    main()
