from __future__ import annotations

from datetime import date

from campsite_finder_agent.cache import (
    cache_file_for_campground,
    cache_file_for_search,
    describe_cached_ranges,
    load_cached_campsites,
    save_cached_campground_campsites,
    save_cached_campsites,
)
from campsite_finder_agent.main import group_searches_by_campground, interleave_search_groups_by_domain, run_scan
from campsite_finder_agent.models import AppConfig, Campsite


def test_cache_round_trips_campsites(tmp_path) -> None:
    search = AppConfig.model_validate(
        {
            "searches": [
                {
                    "name": "camp",
                    "campground": {
                        "name": "Camp",
                        "url": "https://www.reservecalifornia.com/park/707/662",
                    },
                    "date_window": {
                        "start": "2026-08-01",
                        "end": "2026-08-31",
                        "nights": 3,
                    },
                }
            ]
        }
    ).searches[0]
    campsites = [
        Campsite(
            campsite_id="1",
            name="Site 1",
            availabilities={date(2026, 8, 1): "Available"},
        )
    ]

    path = save_cached_campsites(tmp_path, search, campsites)
    loaded = load_cached_campsites(tmp_path, search)

    assert path == cache_file_for_search(tmp_path, search)
    assert loaded == campsites


def test_describe_cached_ranges_for_campground(tmp_path) -> None:
    campground_url = "https://outdoorithm.com/campgrounds/ca/ronald-w-caspers-wilderness-park/ronald-w-caspers-wilderness-park"
    campsite = Campsite(campsite_id="1", name="Site 1")
    save_cached_campground_campsites(tmp_path, campground_url, date(2026, 8, 1), date(2026, 9, 30), [campsite])

    assert describe_cached_ranges(tmp_path, campground_url) == "saved ranges: 2026-08-01 to 2026-09-30"
    assert describe_cached_ranges(tmp_path, "https://example.test/missing") == "no saved ranges for this campground"


def test_use_saved_data_with_save_data_fetches_missing_cache(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "searches.yaml"
    config_path.write_text(
        """
searches:
  - name: camp
    campground:
      name: Camp
      url: https://www.reservecalifornia.com/park/707/662
    date_window:
      start: 2026-08-01
      end: 2026-08-03
      nights: 1
    filters: {}
    require_login: false
    alert:
      methods: [terminal]
"""
    )

    def fake_fetch(*args, **kwargs):
        return [
            Campsite(
                campsite_id="1",
                name="Site 1",
                availabilities={date(2026, 8, 1): "Available"},
            )
        ]

    monkeypatch.setattr("campsite_finder_agent.main.fetch_campsites_for_search", fake_fetch)

    matches = run_scan(
        config_path=config_path,
        cdp_url="http://localhost:9222",
        login_timeout_ms=1,
        request_delay_seconds=0,
        search_delay_seconds=0,
        max_retries=0,
        cache_path=tmp_path / "cache",
        save_data=True,
        use_saved_data=True,
    )

    assert len(matches) == 1
    assert cache_file_for_campground(
        tmp_path / "cache",
        "https://www.reservecalifornia.com/park/707/662",
        date(2026, 8, 1),
        date(2026, 8, 3),
    ).exists()


def test_searches_for_same_campground_fetch_once_for_union_window(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "searches.yaml"
    config_path.write_text(
        """
searches:
  - name: camp-2026
    campground:
      name: Camp
      url: https://www.reservecalifornia.com/park/707/662
    date_window:
      start: 2026-08-01
      end: 2026-08-03
      nights: 1
  - name: camp-2027
    campground:
      name: Camp
      url: https://www.reservecalifornia.com/park/707/662
    date_window:
      start: 2027-06-01
      end: 2027-06-03
      nights: 1
"""
    )
    fetched_windows = []

    def fake_fetch(search, *args, **kwargs):
        fetched_windows.append((search.date_window.start, search.date_window.end))
        return [
            Campsite(
                campsite_id="1",
                name="Site 1",
                availabilities={
                    date(2026, 8, 1): "Available",
                    date(2027, 6, 1): "Available",
                },
            )
        ]

    monkeypatch.setattr("campsite_finder_agent.main.fetch_campsites_for_search", fake_fetch)

    matches = run_scan(
        config_path=config_path,
        cdp_url="http://localhost:9222",
        login_timeout_ms=1,
        request_delay_seconds=0,
        search_delay_seconds=0,
        max_retries=0,
        cache_path=tmp_path / "cache",
        save_data=False,
        use_saved_data=False,
    )

    assert fetched_windows == [(date(2026, 8, 1), date(2027, 6, 3))]
    assert len(matches) == 2


def test_group_searches_by_campground_preserves_rules() -> None:
    config = AppConfig.model_validate(
        {
            "searches": [
                {
                    "name": "camp-a",
                    "campground": {
                        "name": "Camp",
                        "url": "https://www.reservecalifornia.com/park/707/662",
                    },
                    "date_window": {
                        "start": "2026-08-01",
                        "end": "2026-08-03",
                        "nights": 1,
                    },
                },
                {
                    "name": "camp-b",
                    "campground": {
                        "name": "Camp",
                        "url": "https://www.reservecalifornia.com/park/707/662",
                    },
                    "date_window": {
                        "start": "2026-09-01",
                        "end": "2026-09-03",
                        "nights": 3,
                    },
                },
            ]
        }
    )

    groups = group_searches_by_campground(config.searches)

    assert len(groups) == 1
    assert groups[0].start == date(2026, 8, 1)
    assert groups[0].end == date(2026, 9, 3)
    assert groups[0].fetch_search.date_window.nights == 3
    assert [search.name for search in groups[0].searches] == ["camp-a", "camp-b"]


def test_interleave_search_groups_by_domain_round_robins_domains() -> None:
    config = AppConfig.model_validate(
        {
            "searches": [
                {
                    "name": "rc-a",
                    "campground": {"name": "RC A", "url": "https://www.reservecalifornia.com/park/1/1"},
                    "date_window": {"start": "2026-08-01", "end": "2026-08-03", "nights": 1},
                },
                {
                    "name": "rc-b",
                    "campground": {"name": "RC B", "url": "https://www.reservecalifornia.com/park/1/2"},
                    "date_window": {"start": "2026-08-01", "end": "2026-08-03", "nights": 1},
                },
                {
                    "name": "rec-a",
                    "campground": {"name": "Rec A", "url": "https://www.recreation.gov/camping/campgrounds/111111"},
                    "date_window": {"start": "2026-08-01", "end": "2026-08-03", "nights": 1},
                },
                {
                    "name": "rec-b",
                    "campground": {"name": "Rec B", "url": "https://www.recreation.gov/camping/campgrounds/222222"},
                    "date_window": {"start": "2026-08-01", "end": "2026-08-03", "nights": 1},
                },
            ]
        }
    )

    groups = interleave_search_groups_by_domain(group_searches_by_campground(config.searches))

    assert [group.searches[0].name for group in groups] == ["rc-a", "rec-a", "rc-b", "rec-b"]
