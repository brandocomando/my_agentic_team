# Campsite Finder Architecture

The agent has three small layers:

- `recreation.py` attaches to an existing Chrome CDP session, opens the configured campground, optionally waits for login, and fetches Recreation.gov availability JSON from inside the browser session.
- `reserve_california.py` attaches to the same Chrome CDP session and reads ReserveCalifornia grid JSON, including per-day lock metadata used by the pre-release lock icon flow.
- `availability.py` parses campground availability payloads and applies date-window and campsite filters.
- `results.py` aggregates raw campsite matches into reporting windows.
- `ai.py` adds optional Ollama scoring, summaries, and suggested state actions.
- `alerts.py` reports matches through terminal output, terminal bell, and optional Gmail notifications.

The browser layer is intentionally thin. Matching behavior is covered by unit tests without requiring Recreation.gov or Chrome, so selector and API drift can be fixed without disturbing the core search rules.

The agent only discovers availability and alerts. It does not auto-book campsites or submit reservation actions.
