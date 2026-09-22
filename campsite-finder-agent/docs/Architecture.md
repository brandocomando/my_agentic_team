# Campsite Finder Architecture

The agent has three small layers:

- `recreation.py` attaches to an existing Chrome CDP session, opens the configured campground, optionally waits for login, and fetches Recreation.gov availability JSON from inside the browser session.
- `reserve_california.py` attaches to the same Chrome CDP session and reads ReserveCalifornia grid JSON, including per-day lock metadata used by the pre-release lock icon flow.
- `availability.py` parses campground availability payloads and applies date-window and campsite filters.
- `results.py` aggregates raw campsite matches into reporting windows.
- `ai.py` adds optional Ollama scoring, summaries, and suggested state actions.
- `alerts.py` reports matches through terminal output, terminal bell, and optional Gmail notifications.

The browser layer is intentionally thin. Matching behavior is covered by unit tests without requiring Recreation.gov or Chrome, so selector and API drift can be fixed without disturbing the core search rules.

The scan commands discover availability and alert. The get-site helpers can submit reservation/cart actions, stopping before final payment confirmation. ReserveCalifornia release watches initialize the search to the day before the requested arrival for one night, then reload the full page before each availability check because the in-page refresh can retain stale release state. After each reload they restore the previous-day one-night search if needed. The configured interval is a delay between attempts, in addition to reload and setup time. They select the target site's actual arrival-date cell and set `#nights-select` to the requested stay before Book Now. Missing/disabled duration options stop the booking attempt; pre-cart arrival and nights validation remains required before Reserve Unit.
