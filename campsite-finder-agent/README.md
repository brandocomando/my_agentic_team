# Campsite Finder Agent

A local-first Recreation.gov campsite availability watcher. It attaches to a Chrome remote debugging session, waits for Recreation.gov login when requested, checks configured campgrounds for matching date windows, and alerts when a matching site is open.

This first version focuses on discovery and alerting. It does not auto-book or modify reservations.

## Getting Started

This agent is designed to run locally from a browser session you control. It uses Chrome remote debugging so it can reuse your logged-in Recreation.gov session when a provider requires login, while keeping credentials and tokens out of the repo.

### Install

```bash
cd campsite-finder-agent
cp .env.example .env
cp config/searches.example.yaml config/searches.yaml
uv sync --extra dev --extra browser
```

### Start Chrome

Start a dedicated Chrome profile with CDP enabled. Keep this browser open for scans that need a browser session:

```bash
task chrome
```

Log in to Recreation.gov in that Chrome window if needed.

### Configure Searches

Edit `config/searches.yaml` with the campgrounds, dates, nights, filters, and preferences you care about. The checked-in `config/searches.example.yaml` is safe to copy and edit locally.

### Run A Scan

```bash
task scan
```

The scan writes current matches to `data/matches.json` and `data/matches.csv`. Those files are ignored by git.

### Run Tests

```bash
task test
```

## Configuration

Edit `config/searches.yaml`:

```yaml
searches:
  - name: yosemite-upper-pines-thu-sun
    campground:
      name: Yosemite Upper Pines
      url: https://www.recreation.gov/camping/campgrounds/232447
    date_window:
      start: 2026-08-01
      end: 2026-09-30
      nights: 3
      check_in_weekdays: [Thursday]
    filters:
      site_types: [STANDARD NONELECTRIC]
      equipment: Tent
      accessible: false
    require_login: true
    alert:
      methods: [terminal, bell]
```

The example above looks for Thursday check-ins with a Sunday checkout, which is three nights.

Dates can be fixed ISO dates or friendly relative dates. Relative dates resolve at scan startup, which keeps scheduled searches sliding forward:

```yaml
availability:
  start: today
  end: "+2months"
  nights: 3
  check_in_weekdays: [Friday]
```

Supported friendly values include `today`, `tomorrow`, `+10days`, `+2weeks`, and `+2months`. Short forms like `+10d`, `+2w`, and `+2mo` also work. Quote `+...` values in YAML.

Searches and search sets can include AI preferences used by the Ollama review step:

```yaml
preferences:
  likes:
    - beach or coastal campgrounds
    - RV-compatible sites
  dislikes:
    - tent-only sites
    - equestrian sites
  must_haves:
    - three-night stays
  nice_to_haves:
    - short drive from home
  notes: Prefer practical weekend trips over remote primitive camping.
```

## Commands

```bash
task sync
task test
task chrome
task scan
task run -- --config config/searches.yaml --once
```

`scan` writes aggregated availability windows to `data/matches.json` and `data/matches.csv` when matches are found, then prints a compact summary. If no visible matches are found, it removes any existing latest match files instead of writing empty outputs. The output keeps one representative site per campground/check-in date, then merges consecutive check-in dates into a single window so a long run of availability does not flood the report. Use `--watch --interval-seconds 300` to keep polling.

For a system-scheduled hourly run, use cron with the included one-shot script:

```bash
crontab -e
```

Add:

```cron
0 * * * * /opt/personal/my_agentic_team/campsite-finder-agent/scripts/hourly_scan.sh
```

The cron job writes logs to `data/logs/hourly-scan.log`. The script runs one scan, updates the latest `data/matches.json` and `data/matches.csv` when matches are found, removes stale latest files when no visible matches are found, and also keeps timestamped match archives for matching runs.

On macOS, `launchd` is usually more reliable than cron. Install the included hourly LaunchAgent with:

```bash
mkdir -p ~/Library/LaunchAgents
cp launchd/com.bfoster.campsite-finder-agent.hourly.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.bfoster.campsite-finder-agent.hourly.plist
launchctl kickstart -k gui/$(id -u)/com.bfoster.campsite-finder-agent.hourly
```

Check it with:

```bash
launchctl print gui/$(id -u)/com.bfoster.campsite-finder-agent.hourly
tail -n 80 data/logs/hourly-scan.log
tail -n 80 data/logs/launchd.err.log
```

Unload it with:

```bash
launchctl bootout gui/$(id -u)/com.bfoster.campsite-finder-agent.hourly
```

To run the ReserveCalifornia lock scan once per day at 7:00 AM local Mac time, install the daily LaunchAgent:

```bash
mkdir -p ~/Library/LaunchAgents
cp launchd/com.bfoster.campsite-finder-agent.daily-locks.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.bfoster.campsite-finder-agent.daily-locks.plist
```

The daily lock script starts `task chrome` only when Chrome CDP is not already responding, then runs:

```bash
task locks:reservecalifornia
```

Check it with:

```bash
launchctl print gui/$(id -u)/com.bfoster.campsite-finder-agent.daily-locks
tail -n 80 data/logs/daily-lock-scan.log
tail -n 80 data/logs/daily-lock-launchd.err.log
```

Unload it with:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.bfoster.campsite-finder-agent.daily-locks.plist
```

For faster local testing, save fetched campground data once:

```bash
task scan -- --save-data
```

Then rerun matching/report changes without crawling the sites:

```bash
task scan -- --use-saved-data
```

If an earlier save was interrupted, combine both flags to use saved data where it exists and fetch/save only missing searches:

```bash
task scan -- --use-saved-data --save-data
```

The scanner is intentionally throttled to avoid hammering Recreation.gov. By default it waits 2.5 seconds between monthly availability requests, 8 seconds between campgrounds, and backs off longer if Recreation.gov returns a `429` rate-limit response.

Tune those values with:

```bash
task scan -- --request-delay-seconds 5 --search-delay-seconds 15 --max-retries 5
```

For a timed Recreation.gov release-window watch, open Chrome with CDP, sign in if needed, and run the same `get_site` task with a Recreation.gov campground URL:

```bash
task get_site -- SITE=118 START_DATE=3/20/27 NIGHTS=2 CAMPGROUND_URL=https://www.recreation.gov/camping/campgrounds/232250
```

This sets the campground date picker to the requested check-in/check-out before waiting, polls Recreation.gov's month availability endpoint through the attached browser session, refreshes the availability table between polls, and watches the target site for every night in the requested stay. It treats statuses such as `NYR` / `Not Released` as not yet bookable. When all requested nights become available, it opens the campsite detail page, clicks `Add to Cart`, fills order details, accepts the important-information checkbox, clicks `Proceed to Cart`, clicks `Proceed to Payment`, then tries to click `Next` on the payment page if that button is enabled. It never clicks `Confirm`; you take over there. By default it polls once per second from 6:59:30 AM to 7:01:00 AM America/Los_Angeles. Override the window with:

```bash
task get_site -- SITE=118 START_DATE=3/20/27 NIGHTS=2 CAMPGROUND_URL=https://www.recreation.gov/camping/campgrounds/232250 REFRESH_WINDOW_START=06:59:00 REFRESH_WINDOW_END=07:02:00
```

To practice against the current API state without waiting for the release window, use:

```bash
task practice_site -- SITE=118 START_DATE=3/20/27 NIGHTS=2 CAMPGROUND_URL=https://www.recreation.gov/camping/campgrounds/232250
```

Required Recreation.gov get-site values are `SITE`, `START_DATE`, `NIGHTS`, and `CAMPGROUND_URL`, using the same task/env names as ReserveCalifornia. Set them on the task command or persist them in `.env`:

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

For Recreation.gov detection without clicking `Add to Cart`, add `NO_CLICK_BOOK_NOW=1`. To click `Add to Cart` and fill order details but stop before `Proceed to Cart`, add `NO_CLICK_RESERVE_UNIT=1`. To proceed to the payment page but stop before clicking payment `Next`, add `NO_CLICK_PAYMENT_NEXT=1`.

When visible matches are found, the scan tries to score and summarize them with Ollama. Configure Ollama with:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
```

AI analysis adds `ai_score`, `ai_fit`, reasons, concerns, and suggested state actions to the JSON and CSV outputs, plus `data/matches.ai.md`. If Ollama is unavailable, the scan logs a warning and still writes normal match outputs. Disable AI for a run with:

```bash
task scan -- --no-ai
```

AI-scored matches can also send Gmail alerts. The agent uses the same OAuth credential/token pattern as `gmail-inbox-agent`, not an SMTP password:

```env
CAMPSITE_EMAIL_ALERTS_ENABLED=true
GMAIL_CREDENTIALS_PATH=./data/gmail_credentials.json
GMAIL_TOKEN_PATH=./data/gmail_token.json
CAMPSITE_EMAIL_TO=your_email@gmail.com
CAMPSITE_AI_NOTIFY_MIN_SCORE=8.0
CAMPSITE_AI_NOTIFY_ACTIONS=book
CAMPSITE_NOTIFICATION_STATE_PATH=./data/notifications.json
```

An email is sent when a scored match meets the minimum score or has a suggested action in `CAMPSITE_AI_NOTIFY_ACTIONS`. Sent `state_key`s are recorded so the hourly scan does not send the same alert repeatedly. If Gmail auth fails, the scan logs a warning and still writes match outputs. If a copied token cannot refresh, delete `data/gmail_token.json` and run a scan once to complete a fresh OAuth flow.

ReserveCalifornia searches use the site's grid availability endpoint through the attached browser session. The agent requests 21-day grid batches and parses per-site daily availability from the JSON response, which is much faster than clicking through every possible arrival date.

ReserveCalifornia lock icons can be scanned separately from the normal availability matcher. Add `locked_searches` entries using a list of campgrounds plus the same availability, filter, alert, and preference shape as regular searches:

```yaml
locked_searches:
  - name: doheny-south-loop-locked-fri-sun
    campgrounds:
      - name: Doheny SB South Loop
        provider: reservecalifornia
        url: https://www.reservecalifornia.com/park/639/464
      - name: San Clemente SB
        provider: reservecalifornia
        url: https://www.reservecalifornia.com/park/706/432
    availability:
      start: 2026-08-07
      end: 2026-08-10
      nights: 2
      check_in_weekdays: [Friday]
    filters:
      site_type_exclude: []
    preferences:
      likes: [beach access, South Loop]
      must_haves: [locked sites that open at 8am]
```

Then run:

```bash
task locks:reservecalifornia
```

This writes `data/locked-matches.json`, `data/locked-matches.csv`, and AI notes when enabled. It reports stay windows where every night has a non-empty `Lock` value, which is the data behind the lock icon shown before a site opens for booking.

`nights` follows the normal reservation convention: a Friday check-in with `nights: 2` reports a Sunday checkout. For ReserveCalifornia lock scans, the matcher requires lock icons from the check-in date through the checkout date, because a reserved checkout-day cell can prevent booking the full stay.

For one-off debugging, pass the URL and dates directly:

```bash
task locks:reservecalifornia -- --park-url https://www.reservecalifornia.com/park/639/464 --start-date 2026-08-07 --end-date 2026-08-09 --site 90
```

Use `--locks-output data/reservecalifornia-locks.json` or a `.csv` path to write one-off raw lock slices to a file.

For a timed ReserveCalifornia booking assist, open Chrome with CDP, sign in, and run:

```bash
task get_site -- SITE=131 START_DATE=8/21/26 NIGHTS=2 CAMPGROUND_URL=https://www.reservecalifornia.com/park/709/666 OCCUPANT="Your Name"
```

By default this refreshes once per second from 7:59:30 AM to 8:01:00 AM America/Los_Angeles, clicks the matching site cell for `START_DATE` if it becomes selectable, clicks the enabled `Book Now` button, acknowledges an `OK` alert popup if one appears, validates that the reservation details page shows the requested arrival date and `NIGHTS`, fills pre-cart details, accepts terms, clicks `Reserve Unit`, then clicks `Go To Checkout` if it appears. If checkout address fields are configured, it fills those too. It does not complete payment or enter card details. Override the window with:

```bash
task get_site -- SITE=131 START_DATE=8/21/26 NIGHTS=2 CAMPGROUND_URL=https://www.reservecalifornia.com/park/709/666 OCCUPANT="Your Name" REFRESH_WINDOW_START=07:59:00 REFRESH_WINDOW_END=08:02:00
```

To practice on a site that is already open, use the immediate bounded runner:

```bash
task practice_site -- SITE=131 START_DATE=8/21/26 NIGHTS=2 CAMPGROUND_URL=https://www.reservecalifornia.com/park/709/666 OCCUPANT="Your Name"
```

Practice mode polls every 0.2 seconds for up to 20 seconds by default. Override with `REFRESH_INTERVAL_SECONDS=0.1` or `MAX_RUN_SECONDS=60`.

Required booking-assist values are `SITE`, `START_DATE`, `NIGHTS`, `CAMPGROUND_URL`, and `OCCUPANT`. Set them on the task command or persist them in `.env`:

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

Checkout address details can be set with `STREET_1`, `CITY`, `STATE`, and `POSTAL_CODE` task variables or with their `CAMPSITE_GET_SITE_*` `.env` equivalents. `ZIPCODE` and `CAMPSITE_GET_SITE_ZIPCODE` are accepted aliases for `POSTAL_CODE`. If any checkout address value is provided, all four are required. The helper fills address fields on the checkout screen only after `Reserve Unit` and `Go To Checkout`; it still stops before card payment.

For a date-picker-only or grid-selection-only rehearsal, add `NO_CLICK_BOOK_NOW=1`.

Recreation.gov searches also use direct availability API requests through the attached browser session. The agent opens campground pages only when login is required or a fallback fetch is needed.

Outdoorithm can be used as an optional provider when you have an API key:

```yaml
campground:
  name: Yosemite Upper Pines
  provider: outdoorithm
  outdoorithm_id: RecreationDotGov:232447:1074
  url: https://www.recreation.gov/camping/campgrounds/232447
```

Set `OUTDOORITHM_API_KEY` in `.env`. Outdoorithm requires attribution wherever its data is shown, and commercial use requires a license.

## Roadmap

Suggested improvements after the hourly scan has run for a while:

- Add a strict offline mode that never fetches missing cache entries, useful for report and AI prompt testing.
- Add cache coverage tooling that lists which campgrounds/date ranges are saved before a run starts.
- Add per-search AI notification thresholds so beach, mountain, and local searches can alert at different scores.
- Add a small review command that marks `state_key`s as ignored, watched, or booked from the latest CSV/JSON output.
- Add provider health metrics to the hourly log, including 429/503 counts and time spent waiting on retries.
- Add an optional digest email for all good matches, separate from urgent single-match notifications.
