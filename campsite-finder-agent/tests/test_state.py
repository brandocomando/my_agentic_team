from __future__ import annotations

from datetime import date

from campsite_finder_agent.models import MatchWindow
from campsite_finder_agent.state import ResultState, filter_stateful_match_windows, load_state


def make_window(state_key: str) -> MatchWindow:
    return MatchWindow(
        state_key=state_key,
        search_names=["camp"],
        campground_name="Camp",
        campground_url="https://example.test/camp",
        check_in_window_start=date(2026, 8, 1),
        check_in_window_end=date(2026, 8, 1),
        earliest_check_out=date(2026, 8, 4),
        latest_check_out=date(2026, 8, 4),
        nights=3,
        representative_campsite_id="1",
        representative_campsite_name="Site 1",
        representative_site_type="STANDARD",
        representative_loop="",
        matching_start_count=1,
        unique_site_count=1,
    )


def test_load_state_creates_empty_state_file(tmp_path) -> None:
    path = tmp_path / "state.json"

    state = load_state(path)

    assert state == ResultState()
    assert path.read_text() == '{\n  "ignored": [],\n  "booked": []\n}\n'


def test_filter_stateful_match_windows_hides_ignored_and_booked_keys() -> None:
    matches = [make_window("keep"), make_window("ignore"), make_window("book")]
    state = ResultState(
        ignored=[" ignore "],
        booked=[{"state_key": " book ", "note": "Reserved manually"}],
    )

    visible = filter_stateful_match_windows(matches, state)

    assert [match.state_key for match in visible] == ["keep"]
