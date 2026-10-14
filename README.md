# Matkahuolto package tracking for Home Assistant

Home Assistant integration that follows the packages of a Matkahuolto account.

[![GitHub Release][releases-shield]][releases] [![GitHub Release Date][release-date-shield]][releases] [![HACS][hacs-shield]][hacs] [![License][license-shield]](LICENSE)

<img src="https://raw.githubusercontent.com/jesmak/matkahuolto_tracking/main/docs/images/dashboard-light.png#gh-light-mode-only" width="560" alt="A dashboard with the counts of packages on the way and ready for pickup, and package-tracker-card listing a package ready for pickup with its code and deadline, one on its way and one delivered">
<img src="https://raw.githubusercontent.com/jesmak/matkahuolto_tracking/main/docs/images/dashboard-dark.png#gh-dark-mode-only" width="560" alt="A dashboard with the counts of packages on the way and ready for pickup, and package-tracker-card listing a package ready for pickup with its code and deadline, one on its way and one delivered">

## What is it?

A custom component that lists the coming and recently delivered packages of a
[matkahuolto.fi](https://www.matkahuolto.fi/) account. There's no need to add packages by hand. The list comes from
the packages sent to your account, and it's updated every 10 minutes.

The sensor lists the packages in the format [package-tracker-card](https://github.com/jesmak/package-tracker-card)
reads, so the card can show them together with packages from other tracking integrations. Two more sensors count the
packages, and an event entity fires when one of them moves along.

This is an unofficial integration. See [Data](#data) for what that means.

## Installation

### With HACS

1. Add this repository to HACS custom repositories with type **Integration**
2. Search for Matkahuolto package tracking in HACS and download it
3. Restart Home Assistant
4. Add the integration in Settings › Devices & services and log in with your matkahuolto.fi email address and
   password

### Manual

1. Download the source code from the latest release
2. Copy the `custom_components/matkahuolto_tracking` folder to your Home Assistant installation's
   `config/custom_components` folder
3. Restart Home Assistant
4. Add the integration in Settings › Devices & services and log in with your matkahuolto.fi email address and
   password

### Logging in

The integration logs in with the email address and password of your matkahuolto.fi account, the way the Matkahuolto
Paketit app does. The website's login needs a reCAPTCHA, while the app's doesn't, so nothing has to be copied from a
browser.

Home Assistant keeps the password, so that the integration can log in again by itself when its session runs out. It
asks for the password only if Matkahuolto stops accepting it, for example after you change it. Anyone who can read
Home Assistant's configuration or a backup of it can read the password too.

Because the login imitates the app, a change at Matkahuolto's end can stop it. If the setup says Matkahuolto turned
the login away, the integration needs an update.

## Settings

Each account is added separately. To change its settings, or to log in again with a new password, choose
**Reconfigure** from the account's menu on the integration page.

| Name                                       | Type    | Description                                                                      | Default                   |
| ------------------------------------------ | ------- | -------------------------------------------------------------------------------- | ------------------------- |
| Language                                   | enum    | Language of the package event descriptions, `fi` or `en`                         | Home Assistant's language |
| Undelivered packages first                 | boolean | When there are more packages than the maximum, undelivered ones are listed first | on                        |
| Maximum number of packages                 | number  | How many packages the sensor lists                                               | 5                         |
| Days until undelivered packages are hidden | days    | Counted from the latest event. Some packages stay in delivery for good           | 15                        |
| Days until delivered packages are hidden   | days    | Counted from the delivery                                                        | 3                         |
| Pickup code                                | enum    | Don't add, or add                                                                | don't add                 |

The pickup code collects the package, and anyone who can see your dashboard can read it. So it is left out unless
**Pickup code** is set to **Add**. The pickup point itself is always included.

## Sensors

### Packages

The state is the time a package of the account last changed, such as when it was received, moved or delivered. The
sensor is named after the account, for example `sensor.matkahuolto_matti_meikalainen_example_com`.

The `packages` attribute lists the packages, and each package has these keys.

| Key                                 | Description                                                                         |
| ----------------------------------- | ----------------------------------------------------------------------------------- |
| `shipment_number`                   | The shipment's tracking number                                                      |
| `status`                            | The package's status, below                                                         |
| `raw_status`                        | Matkahuolto's own status code                                                       |
| `origin`, `origin_city`             | The sender and its city                                                             |
| `destination`, `destination_city`   | The pickup point and the receiver's city                                            |
| `shipment_date`                     | When the package was sent                                                           |
| `latest_event`, `latest_event_city` | The latest event and where it happened                                              |
| `latest_event_date`                 | When the package last changed                                                       |
| `latest_event_country`              | Always `FI`                                                                         |
| `estimated_delivery`                | When the package is expected, when the service says                                 |
| `pickup_deadline`                   | How long it is kept at the pickup point                                             |
| `weight`                            | The package's weight in kilograms                                                   |
| `package_count`                     | How many parcels the shipment has                                                   |
| `pickup_point`                      | The pickup point, with `name`, `street`, `postal_code`, `city`, `type`, `available` |
| `pickup_code`                       | The code that collects the package, when it is added                                |
| `pickup_qr`                         | Always empty, until it is known which Matkahuolto points scan a QR code             |
| `source`                            | Always `Matkahuolto`                                                                |
| `tracking_url`                      | The package's page on matkahuolto.fi                                                |

| `status` | Meaning                 | Matkahuolto's codes |
| -------- | ----------------------- | ------------------- |
| `1`      | Waiting                 | below 20            |
| `2`      | Received by Matkahuolto | 20–29               |
| `3`      | In transport            | 30–39               |
| `4`      | In delivery             | 40–49               |
| `5`      | Ready for pickup        | 50–59               |
| `0`      | Delivered               | 60 and above        |

A package delivered home has no pickup point. Times are ISO 8601 with the time zone. The packages aren't stored in the
recorder, only the state. The sensor is unavailable while Matkahuolto can't be reached.

### Counts

Two sensors count the packages, so a badge or an automation needs no templating. They count every package of the
account within the days set above, also those the list has no room for.

| Sensor                    | What it counts                              |
| ------------------------- | ------------------------------------------- |
| Packages on the way       | Everything that hasn't finished its journey |
| Packages ready for pickup | The ones waiting at a pickup point          |

## Events

An event entity, **Package**, fires once for everything that happens to a package, so an automation can act on it
without watching the packages attribute. Several packages changing in one update fire one event each, packages the
list has no room for included.

| Event type         | When it fires                                 |
| ------------------ | --------------------------------------------- |
| `new_package`      | A package the account hadn't seen before      |
| `moved`            | The package moved along, or a new event of it |
| `ready_for_pickup` | It is waiting to be picked up                 |
| `delivered`        | It has been delivered                         |

The event carries the package it happened to, with `shipment_number`, `status`, `raw_status`, `origin`,
`destination`, `destination_city`, `latest_event`, `latest_event_city`, `latest_event_date` and `source`.

Nothing fires for the packages that are already there when Home Assistant starts, or when the integration is reloaded,
since they have not just happened. A change while Home Assistant was off fires nothing either.

## Examples

A notification for every package that can be picked up. The trigger watches every event, not only a change of its
type, so the second package ready in a row isn't missed. `queued` keeps the events of one update from being dropped.


```yaml
automation:
  - mode: queued
    triggers:
      - trigger: state
        entity_id: event.matkahuolto_matti_meikalainen_example_com_package
        not_from: unavailable
        not_to:
          - unavailable
          - unknown
    conditions:
      - condition: state
        entity_id: event.matkahuolto_matti_meikalainen_example_com_package
        attribute: event_type
        state: ready_for_pickup
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "{{ trigger.to_state.attributes.shipment_number }} is ready for pickup"
```

The packages on a dashboard, with the codes revealed when clicked:

```yaml
type: custom:package-tracker-card
title: Packages
entity: sensor.matkahuolto_matti_meikalainen_example_com
pickup_code: toggle
```

## Upgrading from 2.1 and earlier

The pickup point is always included now, and the **Pickup point and code** switch became the **Pickup code** choice.
An account that had the switch on gets **Add**, and one that had it off gets **Don't add**.

An account added with tokens, in 1.0.3 or 2.0.0, has no password saved. Choose **Reconfigure** › **Log in again** once
and give it, so that the integration can log in by itself when its session runs out.

The account, the sensors, the event entity, their entity IDs and the other settings all carry over.

## Data

Package data comes from Oy Matkahuolto Ab, from the same service the matkahuolto.fi website and the Matkahuolto
Paketit app use.

This is an unofficial integration. It isn't affiliated with or endorsed by Matkahuolto. Each user logs in with their
own matkahuolto.fi account, and using it may be against Matkahuolto's terms of service, so use it at your own risk. It
will be withdrawn if Matkahuolto objects.

## Translating

The integration's texts are in `custom_components/matkahuolto_tracking/translations/`, one JSON file per language,
named by its language code, such as `en.json` and `fi.json`. To add a language, copy `en.json` to the new language's
code and translate the values.

## Development

Requires Python 3.14, the version the current Home Assistant needs.

```
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
```

| Path                           | What it contains                                       |
| ------------------------------ | ------------------------------------------------------ |
| `__init__.py`                  | Setup, and moving entries of earlier versions          |
| `config_flow.py`               | Logging in, logging in again and changing settings     |
| `api.py`                       | Logging in, Matkahuolto's web service, renewing tokens |
| `coordinator.py`               | Fetching the packages every 10 minutes                 |
| `shipments.py`                 | Turning shipments into the sensor's packages           |
| `sensor.py`                    | The sensors, the account's own and the counts          |
| `event.py`                     | The event entity, one event per package change         |
| `changes.py`                   | What happened to the packages between two updates      |
| `translations/<language>.json` | Home Assistant UI texts                                |
| `docs/screenshots.json`        | The made-up data the README's image is taken from      |

## Support

Hey dude! Help me out for a couple of :beers: or a :coffee:!

[![coffee](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/jesmak)

## License

MIT, see [LICENSE](LICENSE).

[releases-shield]: https://img.shields.io/github/release/jesmak/matkahuolto_tracking.svg?style=for-the-badge
[release-date-shield]: https://img.shields.io/github/release-date/jesmak/matkahuolto_tracking?style=for-the-badge
[releases]: https://github.com/jesmak/matkahuolto_tracking/releases
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[hacs]: https://hacs.xyz/docs/faq/custom_repositories/
[license-shield]: https://img.shields.io/github/license/jesmak/matkahuolto_tracking.svg?style=for-the-badge
