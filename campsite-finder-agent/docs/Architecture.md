# Campsite Finder Architecture

The agent has three small layers:

- `recreation.py` attaches to an existing Chrome CDP session, opens the configured campground, optionally waits for login, and fetches Recreation.gov availability JSON from inside the browser session.
- `availability.py` parses campground availability payloads and applies date-window and campsite filters.
- `alerts.py` reports matches. The first supported methods are terminal output and a terminal bell.

The browser layer is intentionally thin. Matching behavior is covered by unit tests without requiring Recreation.gov or Chrome, so selector and API drift can be fixed without disturbing the core search rules.

The agent only discovers availability and alerts. It does not auto-book campsites or submit reservation actions.
