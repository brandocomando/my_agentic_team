from __future__ import annotations

from datetime import date

from campsite_finder_agent.config import load_config
from campsite_finder_agent.main import expand_locked_searches
from campsite_finder_agent.models import AppConfig, resolve_config_date


def test_global_filters_merge_with_search_filters(tmp_path) -> None:
    path = tmp_path / "searches.yaml"
    path.write_text(
        """
filters:
  site_type_exclude:
    - TENT ONLY
searches:
  - name: camp
    campground:
      name: Camp
      url: https://www.reservecalifornia.com/park/707/662
    date_window:
      start: 2026-08-01
      end: 2026-08-31
      nights: 3
    filters:
      site_type_exclude:
        - Hike/Bike
      min_vehicle_length: 20
"""
    )

    config = load_config(path)

    assert config.searches[0].filters.site_type_exclude == ["TENT ONLY", "Hike/Bike"]
    assert config.searches[0].filters.min_vehicle_length == 20


def test_global_filters_merge_with_locked_search_filters(tmp_path) -> None:
    path = tmp_path / "searches.yaml"
    path.write_text(
        """
filters:
  site_type_exclude:
    - TENT ONLY
locked_searches:
  - name: locked-camp
    campgrounds:
      - name: Camp
        url: https://www.reservecalifornia.com/park/639/464
    availability:
      start: 2026-08-07
      end: 2026-08-09
      nights: 2
    filters:
      site_type_exclude:
        - Hike/Bike
      min_vehicle_length: 20
"""
    )

    config = load_config(path)

    assert config.locked_searches[0].date_window.start == date(2026, 8, 7)
    assert config.locked_searches[0].filters.site_type_exclude == ["TENT ONLY", "Hike/Bike"]
    assert config.locked_searches[0].filters.min_vehicle_length == 20


def test_locked_search_expands_multiple_campgrounds() -> None:
    config = AppConfig.model_validate(
        {
            "locked_searches": [
                {
                    "name": "coastal-locks",
                    "campgrounds": [
                        {"name": "Doheny", "url": "https://www.reservecalifornia.com/park/639/464"},
                        {"name": "San Clemente", "url": "https://www.reservecalifornia.com/park/706/432"},
                    ],
                    "availability": {"start": "2026-08-07", "end": "2026-08-09", "nights": 2},
                    "preferences": {"likes": ["beach"]},
                }
            ]
        }
    )

    searches = expand_locked_searches(config.locked_searches)

    assert [search.campground.name for search in searches] == ["Doheny", "San Clemente"]
    assert {search.name for search in searches} == {"coastal-locks"}
    assert all(search.preferences.likes == ["beach"] for search in searches)


def test_relative_date_strings_resolve_from_today() -> None:
    today = date(2026, 8, 3)

    assert resolve_config_date("today", today=today) == date(2026, 8, 3)
    assert resolve_config_date("tomorrow", today=today) == date(2026, 8, 4)
    assert resolve_config_date("+2weeks", today=today) == date(2026, 8, 17)
    assert resolve_config_date("+2 months", today=today) == date(2026, 10, 3)
    assert resolve_config_date("+10d", today=today) == date(2026, 8, 13)


def test_relative_month_dates_clamp_to_month_end() -> None:
    assert resolve_config_date("+1month", today=date(2026, 1, 31)) == date(2026, 2, 28)


def test_config_accepts_friendly_relative_date_strings(monkeypatch) -> None:
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 8, 3)

    monkeypatch.setattr("campsite_finder_agent.models.date", FixedDate)

    config = AppConfig.model_validate(
        {
            "search_sets": [
                {
                    "name": "next-two-months",
                    "campground_ids": ["ReserveCalifornia:1"],
                    "availability": {
                        "start": "today",
                        "end": "+2months",
                        "nights": 2,
                    },
                }
            ]
        }
    )

    assert config.search_sets[0].availability.start == date(2026, 8, 3)
    assert config.search_sets[0].availability.end == date(2026, 10, 3)
