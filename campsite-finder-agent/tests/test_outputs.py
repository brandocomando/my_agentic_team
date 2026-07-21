from __future__ import annotations

from datetime import date
from pathlib import Path

from campsite_finder_agent.main import discover_state_catalog, run_output_path, write_matches_csv
from campsite_finder_agent.models import MatchWindow


def test_write_matches_csv_includes_campground_link(tmp_path) -> None:
    path = tmp_path / "matches.csv"
    write_matches_csv(
        path,
        [
            MatchWindow(
                state_key="abc123",
                search_names=["san-clemente"],
                campground_id="ReserveCalifornia:707",
                campground_name="San Clemente State Beach - East",
                campground_url="https://www.reservecalifornia.com/park/707/662",
                check_in_window_start=date(2026, 12, 3),
                check_in_window_end=date(2026, 12, 5),
                earliest_check_out=date(2026, 12, 6),
                latest_check_out=date(2026, 12, 8),
                nights=3,
                representative_campsite_id="44624",
                representative_campsite_name="Campsite #100",
                representative_site_type="4303",
                representative_loop="",
                matching_campsite_ids=["44624", "44625"],
                matching_start_count=3,
                unique_site_count=2,
            )
        ],
    )

    csv_text = path.read_text()
    assert "state_key" in csv_text
    assert "abc123" in csv_text
    assert "campground_id" in csv_text
    assert "ReserveCalifornia:707" in csv_text
    assert "matching_campsite_ids" in csv_text
    assert "44624; 44625" in csv_text
    assert "campground_url" in csv_text
    assert "https://www.reservecalifornia.com/park/707/662" in csv_text


def test_run_output_path_adds_run_id_before_extension() -> None:
    assert run_output_path(
        Path("data/matches.json"),
        "20260721-101500-123456",
    ) == Path("data/matches-20260721-101500-123456.json")


def test_discover_state_catalog_writes_state_json(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OUTDOORITHM_API_KEY", "test-key")
    monkeypatch.setattr(
        "campsite_finder_agent.main.discover_campground_catalog_for_state",
        lambda state, api_key: [{"id": "ReserveCalifornia:1", "slug": "ca/camp", "name": "Camp", "nearest_city": "City", "url": "https://example.test"}],
    )

    path = discover_state_catalog("ca")

    assert path == Path("data/CA.json")
    assert path.read_text() == (
        "[\n"
        "  {\n"
        "    \"id\": \"ReserveCalifornia:1\",\n"
        "    \"slug\": \"ca/camp\",\n"
        "    \"name\": \"Camp\",\n"
        "    \"nearest_city\": \"City\",\n"
        "    \"url\": \"https://example.test\"\n"
        "  }\n"
        "]\n"
    )
