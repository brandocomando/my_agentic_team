from __future__ import annotations

from datetime import date

from campsite_finder_agent.models import Match
from campsite_finder_agent.results import aggregate_match_windows, state_key_for_window


def make_match(
    campsite_id: str,
    check_in: date,
    campground_url: str = "https://example.test/camp",
    unlock_times: list[str] | None = None,
) -> Match:
    return Match(
        search_name="camp-thu-sun",
        campground_id="ReserveCalifornia:123",
        campground_name="Camp",
        campground_url=campground_url,
        campsite_id=campsite_id,
        campsite_name=f"Site {campsite_id}",
        check_in=check_in,
        check_out=date.fromordinal(check_in.toordinal() + 3),
        nights=3,
        site_type="",
        loop="",
        availability=["Available", "Available", "Available"],
        unlock_times=unlock_times or [],
    )


def test_aggregate_match_windows_keeps_one_site_per_campground_start_date() -> None:
    windows = aggregate_match_windows(
        [
            make_match("2", date(2026, 8, 6)),
            make_match("1", date(2026, 8, 6)),
        ]
    )

    assert len(windows) == 1
    assert windows[0].check_in_window_start == date(2026, 8, 6)
    assert windows[0].check_in_window_end == date(2026, 8, 6)
    assert windows[0].campground_id == "ReserveCalifornia:123"
    assert windows[0].representative_campsite_id == "1"
    assert windows[0].matching_campsite_ids == ["1", "2"]
    assert windows[0].unique_site_count == 2
    assert windows[0].matching_start_count == 1
    assert windows[0].state_key == state_key_for_window(
        "https://example.test/camp",
        date(2026, 8, 6),
        date(2026, 8, 6),
        3,
    )


def test_aggregate_match_windows_merges_consecutive_start_dates() -> None:
    windows = aggregate_match_windows(
        [
            make_match("1", date(2026, 8, 6)),
            make_match("2", date(2026, 8, 7)),
            make_match("3", date(2026, 8, 8)),
            make_match("4", date(2026, 8, 10)),
        ]
    )

    assert len(windows) == 2
    assert windows[0].check_in_window_start == date(2026, 8, 6)
    assert windows[0].check_in_window_end == date(2026, 8, 8)
    assert windows[0].earliest_check_out == date(2026, 8, 9)
    assert windows[0].latest_check_out == date(2026, 8, 11)
    assert windows[0].matching_start_count == 3
    assert windows[0].unique_site_count == 3
    assert windows[1].check_in_window_start == date(2026, 8, 10)


def test_aggregate_match_windows_includes_unlock_times() -> None:
    windows = aggregate_match_windows(
        [
            make_match("1", date(2026, 8, 6), unlock_times=["2026-08-05T08:00:00"]),
            make_match("2", date(2026, 8, 6), unlock_times=["2026-08-05T08:00:00", "2026-08-05T08:15:00"]),
        ]
    )

    assert windows[0].unlock_times == ["2026-08-05T08:00:00", "2026-08-05T08:15:00"]
