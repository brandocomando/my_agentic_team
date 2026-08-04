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
