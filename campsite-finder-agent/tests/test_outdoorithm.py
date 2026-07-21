from __future__ import annotations

from io import BytesIO
from datetime import date
from urllib.error import HTTPError

from campsite_finder_agent.models import AppConfig, Provider
from campsite_finder_agent.outdoorithm import (
    append_explicit_campground_ids,
    availability_date_chunks,
    campground_catalog_rows,
    discovery_query_params,
    discover_searches_for_search_set,
    fetch_availability,
    name_is_excluded,
    outdoorithm_retry_delay,
    parse_availability,
    write_raw_json,
)
from campsite_finder_agent.providers import infer_provider


def test_parse_outdoorithm_availability_ranges() -> None:
    campsites = parse_availability(
        {
            "data": {
                "campsites": [
                    {
                        "campsite_id": "63127",
                        "campsite_name": "02",
                        "loop_name": "AREA WISHON",
                        "campsite_type": "STANDARD NONELECTRIC",
                        "equipment": ["Tent"],
                        "available_dates": [
                            {
                                "start_date": "2026-08-27",
                                "end_date": "2026-08-30",
                                "nights": 3,
                            }
                        ],
                    }
                ]
            }
        }
    )

    assert len(campsites) == 1
    assert campsites[0].campsite_id == "63127"
    assert campsites[0].name == "02"
    assert campsites[0].site_type == "STANDARD NONELECTRIC"
    assert campsites[0].loop == "AREA WISHON"
    assert campsites[0].availabilities == {
        date(2026, 8, 27): "Available",
        date(2026, 8, 28): "Available",
        date(2026, 8, 29): "Available",
    }


def test_infers_outdoorithm_provider_from_config() -> None:
    search = AppConfig.model_validate(
        {
            "searches": [
                {
                    "name": "upper-pines",
                    "campground": {
                        "name": "Upper Pines",
                        "provider": "outdoorithm",
                        "outdoorithm_id": "RecreationDotGov:232447:1074",
                        "url": "https://www.recreation.gov/camping/campgrounds/232447",
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

    assert infer_provider(search) == Provider.outdoorithm


def test_outdoorithm_discovery_query_params() -> None:
    discovery = AppConfig.model_validate(
        {
            "search_sets": [
                {
                    "name": "ca",
                    "discovery": {
                        "states": ["CA"],
                        "camping_type": "tent",
                        "max_price_per_night": 120,
                        "requires_potable_water": True,
                        "requires_flush_toilets": True,
                    },
                    "availability": {
                        "start": "2026-08-01",
                        "end": "2026-08-31",
                        "nights": 3,
                    },
                }
            ]
        }
    ).search_sets[0].discovery

    assert discovery_query_params(discovery, limit=25) == {
        "limit": 25,
        "state": ["CA"],
        "camping_type": "tent",
        "max_price": 120.0,
        "requires_potable_water": "true",
        "requires_flush_toilets": "true",
    }


def test_discovers_searches_for_search_set(monkeypatch) -> None:
    monkeypatch.setenv("OUTDOORITHM_API_KEY", "test-key")
    monkeypatch.setattr(
        "campsite_finder_agent.outdoorithm.discover_campgrounds",
        lambda *args, **kwargs: [
            {
                "id": "RecreationDotGov:232447:1074",
                "name": "Upper Pines",
                "url": "https://outdoorithm.com/campgrounds/ca/yosemite-national-park/upper-pines",
            },
            {
                "id": "BLM:123",
                "name": "Glamis Flats",
                "url": "https://outdoorithm.com/campgrounds/ca/glamis-flats",
            },
            {
                "id": "ReserveCalifornia:123",
                "name": "Ribbonwood Cg",
                "url": "https://outdoorithm.com/campgrounds/ca/ribbonwood-equestrian-cg",
            },
            {
                "id": "ReserveCalifornia:124",
                "name": "Coulter Campground",
                "url": "https://outdoorithm.com/campgrounds/ca/equestrian-group-camp",
            }
        ],
    )
    search_set = AppConfig.model_validate(
        {
            "search_sets": [
                {
                    "name": "ca",
                    "discovery": {
                        "name_exclude": ["Equestrian", "Group"],
                    },
                    "campground_ids": [
                        "ReserveCalifornia:999",
                        "RecreationDotGov:232447:1074",
                    ],
                    "exclude_campground_ids": [
                        "RecreationDotGov:232447:1074",
                    ],
                    "availability": {
                        "start": "2026-08-01",
                        "end": "2026-08-31",
                        "nights": 3,
                    },
                }
            ]
        }
    ).search_sets[0]

    searches = discover_searches_for_search_set(search_set)

    assert searches[0].name == "ca-reservecalifornia-999"
    assert searches[0].campground.provider == Provider.outdoorithm
    assert searches[0].campground.outdoorithm_id == "ReserveCalifornia:999"
    assert searches[0].require_login is False
    assert len(searches) == 1


def test_append_explicit_campground_ids() -> None:
    campgrounds = append_explicit_campground_ids(
        [{"id": "RecreationDotGov:1", "name": "Camp 1"}],
        ["ReserveCalifornia:2"],
    )

    assert campgrounds == [
        {"id": "RecreationDotGov:1", "name": "Camp 1"},
        {
            "id": "ReserveCalifornia:2",
            "name": "ReserveCalifornia:2",
            "url": "https://outdoorithm.com/campgrounds/ReserveCalifornia%3A2",
        },
    ]


def test_id_only_search_set_does_not_call_discovery(monkeypatch) -> None:
    monkeypatch.setenv("OUTDOORITHM_API_KEY", "test-key")

    def fail_discovery(*args, **kwargs):
        raise AssertionError("discovery should not run for ID-only search sets")

    monkeypatch.setattr("campsite_finder_agent.outdoorithm.discover_campgrounds", fail_discovery)
    search_set = AppConfig.model_validate(
        {
            "search_sets": [
                {
                    "name": "known-camps",
                    "campground_ids": ["ReserveCalifornia:999"],
                    "availability": {
                        "start": "2026-08-01",
                        "end": "2026-08-31",
                        "nights": 3,
                    },
                }
            ]
        }
    ).search_sets[0]

    searches = discover_searches_for_search_set(search_set)

    assert len(searches) == 1
    assert searches[0].campground.outdoorithm_id == "ReserveCalifornia:999"


def test_campground_catalog_rows_extract_lookup_fields() -> None:
    rows = campground_catalog_rows(
        [
            {
                "id": "ReserveCalifornia:2",
                "slug": "ca/b-camp",
                "name": "B Camp",
                "nearest_city": "B City",
                "url": "https://outdoorithm.com/campgrounds/ca/b-camp",
                "ignored": "extra",
            },
            {
                "id": "ReserveCalifornia:1",
                "slug": "ca/a-camp",
                "name": "A Camp",
                "nearest_city": "A City",
                "url": "https://outdoorithm.com/campgrounds/ca/a-camp",
            },
        ]
    )

    assert rows == [
        {
            "id": "ReserveCalifornia:1",
            "slug": "ca/a-camp",
            "name": "A Camp",
            "nearest_city": "A City",
            "url": "https://outdoorithm.com/campgrounds/ca/a-camp",
        },
        {
            "id": "ReserveCalifornia:2",
            "slug": "ca/b-camp",
            "name": "B Camp",
            "nearest_city": "B City",
            "url": "https://outdoorithm.com/campgrounds/ca/b-camp",
        },
    ]


def test_name_exclude_matches_case_insensitive_substrings() -> None:
    assert name_is_excluded("Horse Equestrian Camp", ["equestrian"])
    assert name_is_excluded("Big Group Campground", ["Group"])
    assert name_is_excluded("https://outdoorithm.com/campgrounds/ca/ribbonwood-equestrian-cg", ["Equestrian"])
    assert not name_is_excluded("Buena Vista Aquatic Recreation Area", ["Group"])


def test_outdoorithm_availability_chunks_are_31_days_or_less() -> None:
    chunks = availability_date_chunks(date(2026, 8, 1), date(2026, 10, 5))

    assert chunks == [
        (date(2026, 8, 1), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 10, 1)),
        (date(2026, 10, 2), date(2026, 10, 5)),
    ]


def test_outdoorithm_retry_delay_uses_retry_after_header() -> None:
    class Error:
        headers = {"Retry-After": "12"}

    assert outdoorithm_retry_delay(Error(), 0) == 12


def test_outdoorithm_retry_delay_falls_back_to_capped_backoff() -> None:
    class Error:
        headers = {}

    assert outdoorithm_retry_delay(Error(), 0) == 5
    assert outdoorithm_retry_delay(Error(), 20) == 60


def test_write_raw_json(tmp_path) -> None:
    path = write_raw_json(tmp_path / "raw", "payload.json", {"ok": True})

    assert path == tmp_path / "raw" / "payload.json"
    assert path.read_text() == '{\n  "ok": true\n}\n'


def test_fetch_availability_logs_retryable_errors(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"data": {"campsites": []}}'

    calls = 0

    def fake_urlopen(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError(
                url="https://outdoorithm.test",
                code=429,
                msg="rate limited",
                hdrs={},
                fp=BytesIO(b'{"error": "rate limited"}'),
            )
        return Response()

    sleep_calls: list[float] = []
    messages: list[str] = []
    monkeypatch.setattr("campsite_finder_agent.outdoorithm.urlopen", fake_urlopen)
    monkeypatch.setattr("campsite_finder_agent.outdoorithm.time.sleep", sleep_calls.append)

    payload = fetch_availability(
        "ReserveCalifornia:123",
        date(2026, 8, 1),
        date(2026, 8, 31),
        "test-key",
        max_retries=1,
        retry_logger=messages.append,
    )

    assert payload == {"data": {"campsites": []}}
    assert sleep_calls == [5]
    assert messages == [
        "Outdoorithm returned 429 for ReserveCalifornia:123 2026-08-01 to 2026-08-31; "
        "retrying in 5s (attempt 1/2)."
    ]
