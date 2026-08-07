# Configuration

The main local config file is `config/searches.yaml`.

Create it from the checked-in example:

```bash
cp config/searches.example.yaml config/searches.yaml
```

## Basic Search

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

This example looks for Thursday check-ins with a Sunday checkout, which is three nights.

## Relative Dates

Dates can be fixed ISO dates or friendly relative dates. Relative dates resolve at scan startup, which keeps scheduled searches sliding forward:

```yaml
availability:
  start: today
  end: "+2months"
  nights: 3
  check_in_weekdays: [Friday]
```

Supported friendly values include `today`, `tomorrow`, `+10days`, `+2weeks`, and `+2months`. Short forms like `+10d`, `+2w`, and `+2mo` also work.

Quote `+...` values in YAML.

## Preferences

Searches and search sets can include preferences used by the Ollama review step:

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

## ReserveCalifornia Searches

ReserveCalifornia searches use the site's grid availability endpoint through the attached browser session. The agent requests 21-day grid batches and parses per-site daily availability from the JSON response.

Example:

```yaml
searches:
  - name: reservecalifornia-park-707-662-thu-sun
    campground:
      name: ReserveCalifornia Park 707 662
      provider: reservecalifornia
      url: https://www.reservecalifornia.com/park/707/662
    date_window:
      start: today
      end: +4months
      nights: 3
      check_in_weekdays: [Thursday]
    filters: {}
    require_login: false
    preferences:
      likes: [beach access, RV-compatible]
      dislikes: [primitive, hike-in]
    alert:
      methods: [terminal, bell]
```

## ReserveCalifornia Lock Searches

ReserveCalifornia lock icons can be scanned separately from normal availability. Add `locked_searches` entries using a list of campgrounds plus the same availability, filter, alert, and preference shape as regular searches:

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

`nights` follows the normal reservation convention: a Friday check-in with `nights: 2` reports a Sunday checkout. For ReserveCalifornia lock scans, the matcher requires lock icons from the check-in date through the checkout date, because a reserved checkout-day cell can prevent booking the full stay.

Run configured lock searches with:

```bash
task locks:reservecalifornia
```

## Outdoorithm Searches

Outdoorithm can be used as an optional provider when you have an API key:

```yaml
campground:
  name: Yosemite Upper Pines
  provider: outdoorithm
  outdoorithm_id: RecreationDotGov:232447:1074
  url: https://www.recreation.gov/camping/campgrounds/232447
```

Set `OUTDOORITHM_API_KEY` in `.env`. Outdoorithm requires attribution wherever its data is shown, and commercial use requires a license.
