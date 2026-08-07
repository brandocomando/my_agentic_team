# Commands

Commands are defined in `Taskfile.yml` and run from the `campsite-finder-agent` directory.

## Setup And Tests

```bash
task sync
task test
task chrome
```

- `task sync`: install Python dependencies with `uv`.
- `task test`: run unit tests.
- `task chrome`: start a dedicated Chrome profile with remote debugging enabled.

Keep the `task chrome` window open for browser-backed scans and booking-assist tasks.

## Scans

Run one scan:

```bash
task scan
```

Run one scan without AI:

```bash
task scan -- --no-ai
```

Run the app directly with custom arguments:

```bash
task run -- --config config/searches.yaml --once
```

`scan` writes aggregated availability windows to `data/matches.json` and `data/matches.csv` when matches are found, then prints a compact summary. If no visible matches are found, it removes any existing latest match files instead of writing empty outputs.

The output keeps one representative site per campground/check-in date, then merges consecutive check-in dates into a single window so a long run of availability does not flood the report.

## Watch Mode

Keep scanning until interrupted:

```bash
task watch
```

Poll at a custom interval:

```bash
task run -- --watch --interval-seconds 300
```

There is also an hourly watch task:

```bash
task hourly
```

## Cached And Saved Data

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

## Throttling

The scanner is intentionally throttled to avoid hammering campsite providers. By default it waits 2.5 seconds between monthly availability requests, 8 seconds between campgrounds, and backs off longer if Recreation.gov returns a `429` rate-limit response.

Tune those values with:

```bash
task scan -- --request-delay-seconds 5 --search-delay-seconds 15 --max-retries 5
```

## ReserveCalifornia Lock Scans

Run configured lock searches:

```bash
task locks:reservecalifornia
```

This writes `data/locked-matches.json`, `data/locked-matches.csv`, and AI notes when enabled. It reports stay windows where every night has a non-empty `Lock` value, which is the data behind the lock icon shown before a site opens for booking.

For one-off debugging, pass the URL and dates directly:

```bash
task locks:reservecalifornia -- --park-url https://www.reservecalifornia.com/park/639/464 --start-date 2026-08-07 --end-date 2026-08-09 --site 90
```

Use `--locks-output data/reservecalifornia-locks.json` or a `.csv` path to write one-off raw lock slices to a file.

## Discovery

Discover Outdoorithm campground IDs for a state:

```bash
task discover -- CA
```

This requires `OUTDOORITHM_API_KEY` in `.env`.

## Booking Assist

Booking-assist commands are covered in [Booking Assist](Booking_Assist.md):

```bash
task get_site
task practice_site
task get_recreation_site
task practice_recreation_site
```
