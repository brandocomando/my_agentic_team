from __future__ import annotations

from datetime import date

from campsite_finder_agent.cache import save_cached_campground_campsites
from campsite_finder_agent.main import domain_for_url, maybe_wait_between_network_searches, run_scan
from campsite_finder_agent.models import AppConfig, Campsite


class DummyConsole:
    def print(self, *args, **kwargs) -> None:
        pass


def test_domain_for_url_normalizes_hostname() -> None:
    assert domain_for_url("https://www.ReserveCalifornia.com/park/707/662") == "www.reservecalifornia.com"


def test_delay_skips_different_domains(monkeypatch) -> None:
    calls: list[float] = []
    monkeypatch.setattr("campsite_finder_agent.main.time.sleep", calls.append)

    maybe_wait_between_network_searches(DummyConsole(), 8, "www.reservecalifornia.com", "www.recreation.gov")

    assert calls == []


def test_delay_runs_for_same_domain_network_fetches(monkeypatch) -> None:
    calls: list[float] = []
    monkeypatch.setattr("campsite_finder_agent.main.time.sleep", calls.append)

    maybe_wait_between_network_searches(DummyConsole(), 8, "www.reservecalifornia.com", "www.reservecalifornia.com")

    assert calls == [8]


def test_delay_skips_outdoorithm_domain(monkeypatch) -> None:
    calls: list[float] = []
    monkeypatch.setattr("campsite_finder_agent.main.time.sleep", calls.append)

    maybe_wait_between_network_searches(DummyConsole(), 8, "outdoorithm.com", "outdoorithm.com")

    assert calls == []


def test_cached_search_does_not_force_delay_before_next_network_fetch(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "searches.yaml"
    config_path.write_text(
        """
searches:
  - name: cached
    campground:
      name: Cached
      url: https://www.reservecalifornia.com/park/707/662
    date_window:
      start: 2026-08-01
      end: 2026-08-03
      nights: 1
  - name: missing
    campground:
      name: Missing
      url: https://www.reservecalifornia.com/park/707/663
    date_window:
      start: 2026-08-01
      end: 2026-08-03
      nights: 1
"""
    )
    cache_path = tmp_path / "cache"
    save_cached_campground_campsites(
        cache_path,
        "https://www.reservecalifornia.com/park/707/662",
        date(2026, 8, 1),
        date(2026, 8, 3),
        [Campsite(campsite_id="1", name="Site 1", availabilities={date(2026, 8, 1): "Available"})],
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr("campsite_finder_agent.main.time.sleep", sleep_calls.append)
    monkeypatch.setattr(
        "campsite_finder_agent.main.fetch_campsites_for_search",
        lambda *args, **kwargs: [
            Campsite(campsite_id="2", name="Site 2", availabilities={date(2026, 8, 1): "Available"})
        ],
    )

    matches = run_scan(
        config_path=config_path,
        cdp_url="http://localhost:9222",
        login_timeout_ms=1,
        request_delay_seconds=0,
        search_delay_seconds=8,
        max_retries=0,
        cache_path=cache_path,
        save_data=True,
        use_saved_data=True,
    )

    assert len(matches) == 2
    assert sleep_calls == []
