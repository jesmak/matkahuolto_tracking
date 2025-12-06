# Matkahuolto package tracking for Home Assistant

## What is it?

A custom component that integrates with Matkahuolto to retrieve information about coming and recently delivered packages.
The big idea of this integration is that one does not have to manually add packages in order to track them, but the list
is updated automatically by retrieving tracking data from the user's account.

## Installation

### With HACS

1. Add this repository to HACS custom repositories
2. Search for Matkahuolto package tracking in HACS and install with type integration
3. Restart Home Assistant
4. Enter your access and refresh tokens and configure other settings as you wish

### Manual

1. Download source code from latest release tag
2. Copy custom_components/matkahuolto_tracking folder to your Home Assistant installation's config/custom_components folder.
3. Restart Home Assistant
4. Configure the integration by adding a new integration in settings/integrations page of Home Assistant
5. Enter your access and refresh tokens and configre other settings as you wish

### How to get the tokens

This guide is done using Google Chrome. If you use some other browser, adjust accordingly.

1. Go to matkahuolto.fi and log out if you are already logged in
2. Open developer console by pressing F12
3. Open network tab
4. Enter auth to filter field
5. Log in to your matkahuolto.fi account
6. Click the auth request that should now have appeared to the request list
7. Open response tab of the request
8. Copy the access token and refresh token values from the response to the integration configuration. Note: Do NOT include the quotation marks around the token values.

<img width="886" height="501" alt="image" src="https://github.com/user-attachments/assets/30cdd819-d1c7-4d57-a575-3a3a9240bb35" />

### Integration settings

| Name                         | Type    | Requirement  | Description                                          | Default             |
| ---------------------------- | ------- | ------------ | ---------------------------------------------------- | ------------------- |
| username                     | string  | **Required** | Username of your Matkahuolto account (your email)    |                     |
| access_token                 | string  | **Required** | Access token of your login to Matkahuolto            |                     |
| refresh_token                | string  | **Required** | Refresh token of your login to Matkahuolto           |                     |
| language                     | string  | **Required** | Used language (fi or en)                             | `en`                |
| prioritize_undelivered       | boolean | **Required** | Toggle this if you want undelivered packages to be shown first, when there are more than the maximum allowed amount of packages available | `true`              |
| max_shipments                | int     | **Required** | Maximum number of packages to retrieve               | `5`                 |
| stale_shipment_day_limit     | int     | **Required** | After how many days a stalled shipment gets hidden? Sometimes shipments stay in "in delivery" state indefinitely | `15`              |
| completed_shipment_day_shown | int     | **Required** | After how many days are completed deliveries hidden? | `3`                 |
