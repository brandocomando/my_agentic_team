# Campsite Finder Agent

A local-first campsite availability watcher for Recreation.gov, ReserveCalifornia, and optional Outdoorithm-backed discovery. It attaches to a Chrome remote debugging session, checks configured campgrounds for matching date windows, and alerts when a matching site is open.

This agent focuses on discovery, alerting, lock-window prep, and booking assistance. It does not complete payment or click final confirmation buttons.

## Quick Start

If this is a brand-new Mac or you are new to Python, start here:

1. Follow [Fresh Mac Setup](docs/Fresh_Mac_Setup.md).
2. Copy the local config files:

   ```bash
   cp .env.example .env
   cp config/searches.example.yaml config/searches.yaml
   ```

3. Install the project dependencies:

   ```bash
   task sync
   ```

4. Start the dedicated browser session:

   ```bash
   task chrome
   ```

5. In that Chrome window, log in to Recreation.gov and/or ReserveCalifornia if your searches need a signed-in session.
6. Run a safe first scan without AI:

   ```bash
   task scan -- --no-ai
   ```

The scan writes current matches to `data/matches.json` and `data/matches.csv` when visible matches are found. Those files are ignored by git.

## Documentation

- [Fresh Mac Setup](docs/Fresh_Mac_Setup.md): install Homebrew, Git, `uv`, `task`, Chrome, clone the repo, and verify the setup.
- [Configuration](docs/Configuration.md): edit `config/searches.yaml`, define dates, filters, preferences, ReserveCalifornia locks, and Outdoorithm searches.
- [Commands](docs/Commands.md): run scans, tests, watch mode, cached/offline reruns, discovery, and lock scans.
- [Booking Assist](docs/Booking_Assist.md): safely practice and run Recreation.gov or ReserveCalifornia release-window helpers.
- [Optional Services](docs/Optional_Services.md): configure Ollama AI scoring, Gmail alerts, and Outdoorithm.
- [Scheduling](docs/Scheduling.md): install hourly and daily macOS scheduled jobs.
- [Troubleshooting](docs/Troubleshooting.md): common first-run errors and fixes.
- [Architecture](docs/Architecture.md): how the agent is organized internally.

## Common Commands

```bash
task sync
task test
task chrome
task scan -- --no-ai
task scan
task watch
task locks:reservecalifornia
task practice_site -- NO_CLICK_BOOK_NOW=1
```

See [Commands](docs/Commands.md) for the full task list.

## Safety Notes

Booking-assist tasks can click meaningful reservation buttons. Practice with safety flags before a real release window:

```bash
task practice_site -- NO_CLICK_BOOK_NOW=1
task practice_site -- NO_CLICK_RESERVE_UNIT=1
```

The helper can fill pre-cart details and advance toward checkout, but it does not enter card details or click final payment confirmation. See [Booking Assist](docs/Booking_Assist.md) before using it on a real release.

## Roadmap

Suggested improvements after the hourly scan has run for a while:

- Add a strict offline mode that never fetches missing cache entries, useful for report and AI prompt testing.
- Add cache coverage tooling that lists which campgrounds/date ranges are saved before a run starts.
- Add per-search AI notification thresholds so beach, mountain, and local searches can alert at different scores.
- Add a small review command that marks `state_key`s as ignored, watched, or booked from the latest CSV/JSON output.
- Add provider health metrics to the hourly log, including 429/503 counts and time spent waiting on retries.
- Add an optional digest email for all good matches, separate from urgent single-match notifications.
