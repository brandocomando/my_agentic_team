from __future__ import annotations

from campsite_finder_agent.config import load_config


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
