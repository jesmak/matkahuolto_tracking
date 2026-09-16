# Matkahuolto package tracking for Home Assistant

Home Assistant integration that follows the packages of a Matkahuolto account.

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)
[![GitHub Activity][commits-shield]][commits]

## Support

Hey dude! Help me out for a couple of :beers: or a :coffee:!

[![coffee](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/jesmak)

## What is it?

A custom component that lists the coming and recently delivered packages of a
[matkahuolto.fi](https://www.matkahuolto.fi/) account. There's no need to add packages by hand: the list comes from
the packages sent to your account, and it's updated every 10 minutes.

The sensor's attributes list the packages in the same format as
[Posti package tracking](https://github.com/jesmak/posti_tracking), so
[package-tracker-card](https://github.com/jesmak/package-tracker-card) can show packages from both.

## Installation

### With HACS

1. Add this repository to HACS custom repositories with type **Integration**
2. Search for Matkahuolto package tracking in HACS and download it
3. Restart Home Assistant
4. Add the integration in Settings › Devices & services, with the tokens described below

### Manual

1. Download the source code from the latest release
2. Copy the `custom_components/matkahuolto_tracking` folder to your Home Assistant installation's
   `config/custom_components` folder
3. Restart Home Assistant
4. Add the integration in Settings › Devices & services, with the tokens described below

## Getting the tokens

The integration signs in with the tokens of a login to matkahuolto.fi, not with a password. You copy them from your
browser once. After that the integration renews the access token by itself, and when the refresh token eventually stops
working too, Home Assistant asks for new tokens on the integration page.

This guide uses Google Chrome. With another browser, adjust accordingly.

1. Go to matkahuolto.fi and log out if you are already logged in
2. Open the developer tools by pressing F12
3. Open the Network tab
4. Enter `auth` in the filter field
5. Log in to your matkahuolto.fi account
6. Click the auth request that appears in the request list
7. Open the Response tab of the request
8. Copy the access token and refresh token values from the response into the integration's settings. Quotation marks
   around the values don't matter; they are removed.

<img width="886" height="501" alt="The access and refresh tokens in the login response, in Chrome's developer tools" src="https://github.com/user-attachments/assets/30cdd819-d1c7-4d57-a575-3a3a9240bb35" />

## Settings

Each account is added separately. To change its tokens or settings later, choose **Reconfigure** from the account's
menu on the integration page.

| Name                                       | Type    | Description                                                                      | Default                   |
| ------------------------------------------ | ------- | -------------------------------------------------------------------------------- | ------------------------- |
| Email address                              | string  | The email address of your matkahuolto.fi account. The sensor is named after it   |                           |
| Access token                               | string  | The access token of your login                                                   |                           |
| Refresh token                              | string  | The refresh token of your login                                                  |                           |
| Language                                   | enum    | Language of the package event descriptions: `fi` or `en`                         | Home Assistant's language |
| Undelivered packages first                 | boolean | When there are more packages than the maximum, undelivered ones are listed first | on                        |
| Maximum number of packages                 | number  | How many packages the sensor lists                                               | 5                         |
| Days until undelivered packages are hidden | days    | Counted from the latest event. Some packages stay in delivery for good           | 15                        |
| Days until delivered packages are hidden   | days    | Counted from the delivery                                                        | 3                         |

## Sensor

The state is the time a package of the account last changed, such as when it was received, moved or delivered. The
sensor is named after the account, for example `sensor.matkahuolto_matti_meikalainen_example_com`.

The `packages` attribute lists the packages, and each package has:

| Key                                 | Description                              |
| ----------------------------------- | ---------------------------------------- |
| `shipment_number`                   | The shipment's tracking number           |
| `status`                            | The package's status, below              |
| `raw_status`                        | Matkahuolto's own status code            |
| `origin`, `origin_city`             | The sender and its city                  |
| `destination`, `destination_city`   | The pickup point and the receiver's city |
| `shipment_date`                     | When the package was sent                |
| `latest_event`, `latest_event_city` | The latest event and where it happened   |
| `latest_event_date`                 | When the package last changed            |
| `latest_event_country`              | Always `FI`                              |
| `source`                            | Always `Matkahuolto`                     |

| `status` | Meaning                 | Matkahuolto's codes |
| -------- | ----------------------- | ------------------- |
| `1`      | Waiting                 | below 20            |
| `2`      | Received by Matkahuolto | 20–29               |
| `3`      | In transport            | 30–39               |
| `4`      | In delivery             | 40–49               |
| `5`      | Ready for pickup        | 50–59               |
| `0`      | Delivered               | 60 and above        |

Times are ISO 8601 with the time zone. The packages aren't stored in the recorder, only the state. The sensor is
unavailable while Matkahuolto can't be reached.

## Upgrading from 1.x

Nothing needs to be done: the account, the sensor and its attributes carry over.

## Data

Package data: Oy Matkahuolto Ab, from the same service the matkahuolto.fi website uses.

## Development

Requires Python 3.14.

```
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check .
```

| Path                           | What it contains                                          |
| ------------------------------ | --------------------------------------------------------- |
| `__init__.py`                  | Setup, and giving entries of earlier versions a unique id |
| `config_flow.py`               | Adding an account, new tokens and changing settings       |
| `api.py`                       | Matkahuolto's web service and renewing the access token   |
| `coordinator.py`               | Fetching the packages every 10 minutes                    |
| `shipments.py`                 | Turning shipments into the sensor's packages              |
| `sensor.py`                    | The sensor                                                |
| `translations/<language>.json` | Home Assistant UI texts                                   |

[commits-shield]: https://img.shields.io/github/commit-activity/y/jesmak/matkahuolto_tracking.svg?style=for-the-badge
[commits]: https://github.com/jesmak/matkahuolto_tracking/commits/master
[license-shield]: https://img.shields.io/github/license/jesmak/matkahuolto_tracking.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/jesmak/matkahuolto_tracking.svg?style=for-the-badge
[releases]: https://github.com/jesmak/matkahuolto_tracking/releases
