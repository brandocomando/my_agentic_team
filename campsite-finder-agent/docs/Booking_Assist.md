# Booking Assist

Booking-assist tasks can click meaningful reservation buttons. Practice with safety flags before a real release-window run.

The helper does not enter card details and does not click final payment confirmation.

## Browser Requirements

Open Chrome with CDP and sign in first:

```bash
task chrome
```

Keep that Chrome window open.

## Safety Flags

Use these flags while learning:

```bash
NO_CLICK_BOOK_NOW=1
NO_CLICK_RESERVE_UNIT=1
NO_CLICK_PAYMENT_NEXT=1
```

- `NO_CLICK_BOOK_NOW=1`: select or inspect only; do not click the main booking button.
- `NO_CLICK_RESERVE_UNIT=1`: fill details but stop before the pre-cart reserve/proceed action.
- `NO_CLICK_PAYMENT_NEXT=1`: for Recreation.gov, stop on the payment page instead of clicking payment `Next`.

Example safe practice run:

```bash
task practice_site -- SITE=131 START_DATE=8/21/26 NIGHTS=2 CAMPGROUND_URL=https://www.reservecalifornia.com/park/709/666 OCCUPANT="Your Name" NO_CLICK_BOOK_NOW=1
```

## Recreation.gov Release Watch

For a timed Recreation.gov release-window watch, open Chrome with CDP, sign in if needed, and run the same `get_site` task with a Recreation.gov campground URL:

```bash
task get_site -- SITE=118 START_DATE=3/20/27 NIGHTS=2 CAMPGROUND_URL=https://www.recreation.gov/camping/campgrounds/232250
```

This sets the campground date picker to the requested check-in/check-out before waiting, polls Recreation.gov's month availability endpoint through the attached browser session, refreshes the availability table between polls, and watches the target site for every night in the requested stay.

It treats statuses such as `NYR` / `Not Released` as not yet bookable. When all requested nights become available, it opens the campsite detail page, clicks `Add to Cart`, fills order details, accepts the important-information checkbox, clicks `Proceed to Cart`, clicks `Proceed to Payment`, then tries to click `Next` on the payment page if that button is enabled. It never clicks `Confirm`; you take over there.

By default it polls once per second from 6:59:30 AM to 7:01:00 AM America/Los_Angeles. Override the window with:

```bash
task get_site -- SITE=118 START_DATE=3/20/27 NIGHTS=2 CAMPGROUND_URL=https://www.recreation.gov/camping/campgrounds/232250 REFRESH_WINDOW_START=06:59:00 REFRESH_WINDOW_END=07:02:00
```

Practice against the current API state without waiting for the release window:

```bash
task practice_site -- SITE=118 START_DATE=3/20/27 NIGHTS=2 CAMPGROUND_URL=https://www.recreation.gov/camping/campgrounds/232250
```

Required Recreation.gov get-site values are `SITE`, `START_DATE`, `NIGHTS`, and `CAMPGROUND_URL`.

Set them on the task command or persist them in `.env`:

```env
CAMPSITE_GET_SITE_SITE=118
CAMPSITE_GET_SITE_START_DATE=3/20/27
CAMPSITE_GET_SITE_NIGHTS=2
CAMPSITE_GET_SITE_CAMPGROUND_URL=https://www.recreation.gov/camping/campgrounds/232250
CAMPSITE_GET_SITE_REFRESH_WINDOW_START=06:59:30
CAMPSITE_GET_SITE_REFRESH_WINDOW_END=07:01:00
CAMPSITE_GET_SITE_REFRESH_INTERVAL_SECONDS=1.0
```

Recreation.gov order details use the same generic get-site personal defaults:

```env
CAMPSITE_GET_SITE_ADULTS=2
CAMPSITE_GET_SITE_CHILDREN=2
CAMPSITE_GET_SITE_PHONE_NUMBER=5551234567
CAMPSITE_GET_SITE_POSTAL_CODE=95814
CAMPSITE_GET_SITE_CAMPING_UNIT=Trailer
CAMPSITE_GET_SITE_TRAILER_LENGTH_FEET=18
CAMPSITE_GET_SITE_VEHICLE_COUNT=1
```

With those `.env` values set, this is enough:

```bash
task practice_site
```

`task get_recreation_site` and `task practice_recreation_site` are also available as explicit Recreation.gov aliases, but `get_site` / `practice_site` infer the provider from `CAMPGROUND_URL`.

## ReserveCalifornia Release Watch

For a timed ReserveCalifornia booking assist, open Chrome with CDP, sign in, and run:

```bash
task get_site -- SITE=131 START_DATE=8/21/26 NIGHTS=2 CAMPGROUND_URL=https://www.reservecalifornia.com/park/709/666 OCCUPANT="Your Name"
```

By default this refreshes once per second from 7:59:30 AM to 8:01:00 AM America/Los_Angeles, clicks the matching site cell for `START_DATE` if it becomes selectable, clicks the enabled `Book Now` button, acknowledges an `OK` alert popup if one appears, validates that the reservation details page shows the requested arrival date and `NIGHTS`, fills pre-cart details, accepts terms, clicks `Reserve Unit`, then clicks `Go To Checkout` if it appears.

If checkout address fields are configured, it fills those too. It does not complete payment or enter card details.

Override the window with:

```bash
task get_site -- SITE=131 START_DATE=8/21/26 NIGHTS=2 CAMPGROUND_URL=https://www.reservecalifornia.com/park/709/666 OCCUPANT="Your Name" REFRESH_WINDOW_START=07:59:00 REFRESH_WINDOW_END=08:02:00
```

Practice on a site that is already open:

```bash
task practice_site -- SITE=131 START_DATE=8/21/26 NIGHTS=2 CAMPGROUND_URL=https://www.reservecalifornia.com/park/709/666 OCCUPANT="Your Name"
```

Practice mode polls every 0.2 seconds for up to 20 seconds by default. Override with `REFRESH_INTERVAL_SECONDS=0.1` or `MAX_RUN_SECONDS=60`.

Required booking-assist values are `SITE`, `START_DATE`, `NIGHTS`, `CAMPGROUND_URL`, and `OCCUPANT`.

Set them on the task command or persist them in `.env`:

```env
CAMPSITE_GET_SITE_SITE="Campsite #G048"
CAMPSITE_GET_SITE_START_DATE=8/21/26
CAMPSITE_GET_SITE_NIGHTS=2
CAMPSITE_GET_SITE_CAMPGROUND_URL=https://www.reservecalifornia.com/park/7/365
CAMPSITE_GET_SITE_OCCUPANT="Your Name"
CAMPSITE_GET_SITE_ADULTS=2
CAMPSITE_GET_SITE_CHILDREN=2
CAMPSITE_GET_SITE_CAMPING_UNIT=Trailer
CAMPSITE_GET_SITE_TRAILER_LENGTH_FEET=18
CAMPSITE_GET_SITE_STREET_1="123 Main St"
CAMPSITE_GET_SITE_CITY=Sacramento
CAMPSITE_GET_SITE_STATE=CA
CAMPSITE_GET_SITE_POSTAL_CODE=95814
```

Task command values override `.env` values. With those `.env` values set, this is enough:

```bash
task practice_site -- NO_CLICK_RESERVE_UNIT=1
```

`OCCUPANT` is the task variable name. In `.env`, use `CAMPSITE_GET_SITE_OCCUPANT`; `CAMPSITE_GET_SITE_OCCUPANT_NAME` is also accepted for compatibility.

Vehicle length is set to the smallest non-`No Vehicle` option that fits `TRAILER_LENGTH` or `CAMPSITE_GET_SITE_TRAILER_LENGTH_FEET`. For example, an 18-foot trailer chooses `< 24` when that option is available. If no option fits, the command fails before clicking `Reserve Unit`. If no trailer length is configured, it falls back to the smallest non-`No Vehicle` option.

Checkout address details can be set with `STREET_1`, `CITY`, `STATE`, and `POSTAL_CODE` task variables or with their `CAMPSITE_GET_SITE_*` `.env` equivalents. `ZIPCODE` and `CAMPSITE_GET_SITE_ZIPCODE` are accepted aliases for `POSTAL_CODE`.

If any checkout address value is provided, all four are required. The helper fills address fields on the checkout screen only after `Reserve Unit` and `Go To Checkout`; it still stops before card payment.
