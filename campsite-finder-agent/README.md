# Campsite Finder Agent

A local-first Recreation.gov campsite availability watcher. It attaches to a Chrome remote debugging session, waits for Recreation.gov login when requested, checks configured campgrounds for matching date windows, and alerts when a matching site is open.

This first version focuses on discovery and alerting. It does not auto-book or modify reservations.

## Setup

```bash
cd campsite-finder-agent
cp .env.example .env
cp config/searches.example.yaml config/searches.yaml
uv sync --extra dev --extra browser
```

Start a dedicated Chrome profile with CDP enabled:

```bash
task chrome
```

Log in to Recreation.gov in that Chrome window if needed, then run:

```bash
task scan
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

## Commands

```bash
task sync
task test
task chrome
task scan
task run -- --config config/searches.yaml --once
```

`scan` writes aggregated availability windows to `data/matches.json` and `data/matches.csv`, then prints a compact summary. The output keeps one representative site per campground/check-in date, then merges consecutive check-in dates into a single window so a long run of availability does not flood the report. Use `--watch --interval-seconds 300` to keep polling.

For a system-scheduled hourly run, use cron with the included one-shot script:

```bash
crontab -e
```

Add:

```cron
0 * * * * /Users/bfoster/Documents/my_agentic_team/campsite-finder-agent/scripts/hourly_scan.sh
```

The cron job writes logs to `data/logs/hourly-scan.log`. The script runs one scan, updates the latest `data/matches.json` and `data/matches.csv`, and also keeps timestamped match archives.

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

ReserveCalifornia searches use the site's grid availability endpoint through the attached browser session. The agent requests 21-day grid batches and parses per-site daily availability from the JSON response, which is much faster than clicking through every possible arrival date.

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
