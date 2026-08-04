from __future__ import annotations

from datetime import date

from campsite_finder_agent.availability import (
    availability_api_url,
    candidate_check_ins,
    facility_id_from_url,
    find_matches,
    merge_campsites,
    month_starts,
    parse_campsites,
)
from campsite_finder_agent.models import AppConfig, Campsite, Provider
from campsite_finder_agent.providers import infer_provider
from campsite_finder_agent.recreation import fetch_json_from_request_context, is_rate_limit_error
from campsite_finder_agent.reserve_california import (
    grid_date_batches,
    infer_selected_stay_availabilities,
    infer_visible_availabilities,
    parse_grid_campsites,
    reserve_california_ids_from_url,
)


def test_facility_id_from_recreation_url() -> None:
    assert facility_id_from_url("https://www.recreation.gov/camping/campgrounds/232447") == "232447"


def test_month_starts_span_range() -> None:
    assert month_starts(date(2026, 8, 15), date(2026, 10, 2)) == [
        date(2026, 8, 1),
        date(2026, 9, 1),
        date(2026, 10, 1),
    ]


def test_availability_api_url_uses_month_start() -> None:
    assert availability_api_url("232447", date(2026, 8, 1)).endswith(
        "/232447/month?start_date=2026-08-01T00%3A00%3A00.000Z"
    )


def test_find_matches_for_thursday_to_sunday() -> None:
    search = AppConfig.model_validate(
        {
            "searches": [
                {
                    "name": "upper-pines",
                    "campground": {
                        "name": "Upper Pines",
                        "url": "https://www.recreation.gov/camping/campgrounds/232447",
                        "outdoorithm_id": "RecreationDotGov:232447:1074",
                    },
                    "date_window": {
                        "start": "2026-08-01",
                        "end": "2026-08-31",
                        "nights": 3,
                        "check_in_weekdays": ["Thursday"],
                    },
                    "filters": {"site_types": ["STANDARD NONELECTRIC"], "equipment": "Tent"},
                }
            ]
        }
    ).searches[0]
    campsites = parse_campsites(
        {
            "campsites": {
                "101": {
                    "campsite_id": "101",
                    "site": "101",
                    "campsite_type": "STANDARD NONELECTRIC",
                    "type_of_use": "Tent",
                    "loop": "A",
                    "availabilities": {
                        "2026-08-06T00:00:00Z": "Available",
                        "2026-08-07T00:00:00Z": "Available",
                        "2026-08-08T00:00:00Z": "Available",
                    },
                },
                "102": {
                    "campsite_id": "102",
                    "site": "102",
                    "campsite_type": "STANDARD NONELECTRIC",
                    "type_of_use": "Tent",
                    "availabilities": {
                        "2026-08-06T00:00:00Z": "Available",
                        "2026-08-07T00:00:00Z": "Reserved",
                        "2026-08-08T00:00:00Z": "Available",
                    },
                },
            }
        }
    )

    matches = find_matches(search, campsites)

    assert len(matches) == 1
    assert matches[0].campground_id == "RecreationDotGov:232447:1074"
    assert matches[0].campsite_id == "101"
    assert matches[0].check_in == date(2026, 8, 6)
    assert matches[0].check_out == date(2026, 8, 9)


def test_site_type_exclude_filters_site_type_text() -> None:
    search = AppConfig.model_validate(
        {
            "searches": [
                {
                    "name": "exclude-tent-only",
                    "campground": {
                        "name": "Quaking Aspen",
                        "url": "https://www.recreation.gov/camping/campgrounds/232827",
                    },
                    "date_window": {
                        "start": "2027-05-28",
                        "end": "2027-06-05",
                        "nights": 5,
                    },
                    "filters": {"site_type_exclude": ["TENT ONLY"]},
                }
            ]
        }
    ).searches[0]
    campsites = parse_campsites(
        {
            "campsites": {
                "88794": {
                    "campsite_id": "88794",
                    "site": "A",
                    "campsite_type": "GROUP TENT ONLY AREA NONELECTRIC",
                    "availabilities": {
                        "2027-05-28T00:00:00Z": "Available",
                        "2027-05-29T00:00:00Z": "Available",
                        "2027-05-30T00:00:00Z": "Available",
                        "2027-05-31T00:00:00Z": "Available",
                        "2027-06-01T00:00:00Z": "Available",
                    },
                }
            }
        }
    )

    assert find_matches(search, campsites) == []


def test_site_type_exclude_filters_campsite_name_text() -> None:
    search = AppConfig.model_validate(
        {
            "searches": [
                {
                    "name": "exclude-hike-bike",
                    "campground": {
                        "name": "Carpinteria Anacapa",
                        "url": "https://www.reservecalifornia.com/park/6/357",
                    },
                    "date_window": {
                        "start": "2026-08-27",
                        "end": "2026-08-31",
                        "nights": 4,
                    },
                    "filters": {"site_type_exclude": ["Hike/Bike"]},
                }
            ]
        }
    ).searches[0]
    campsites = [
        Campsite(
            campsite_id="4645",
            name="Hike/Bike Campsite #HB12",
            site_type="4320",
            availabilities={
                date(2026, 8, 27): "Available",
                date(2026, 8, 28): "Available",
                date(2026, 8, 29): "Available",
                date(2026, 8, 30): "Available",
            },
        )
    ]

    assert find_matches(search, campsites) == []


def test_site_type_exclude_filters_punctuation_variants() -> None:
    search = AppConfig.model_validate(
        {
            "searches": [
                {
                    "name": "exclude-tent-only",
                    "campground": {
                        "name": "Camp",
                        "url": "https://www.recreation.gov/camping/campgrounds/123456",
                    },
                    "date_window": {
                        "start": "2026-08-01",
                        "end": "2026-08-02",
                        "nights": 1,
                    },
                    "filters": {"site_type_exclude": ["TENT ONLY"]},
                }
            ]
        }
    ).searches[0]
    campsites = [
        Campsite(
            campsite_id="1",
            name="Site 1",
            site_type="TENT-ONLY NONELECTRIC",
            availabilities={date(2026, 8, 1): "Available"},
        )
    ]

    assert find_matches(search, campsites) == []


def test_candidate_check_ins_honor_weekday_and_nights() -> None:
    search = AppConfig.model_validate(
        {
            "searches": [
                {
                    "name": "weekends",
                    "campground": {
                        "name": "Camp",
                        "url": "https://www.recreation.gov/camping/campgrounds/123456",
                    },
                    "date_window": {
                        "start": "2026-08-01",
                        "end": "2026-08-15",
                        "nights": 3,
                        "check_in_weekdays": ["Thursday"],
                    },
                }
            ]
        }
    ).searches[0]

    assert candidate_check_ins(search) == [date(2026, 8, 6)]


def test_merge_campsites_combines_month_availability() -> None:
    august = parse_campsites(
        {"campsites": {"1": {"site": "1", "availabilities": {"2026-08-31T00:00:00Z": "Available"}}}}
    )
    september = parse_campsites(
        {"campsites": {"1": {"site": "1", "availabilities": {"2026-09-01T00:00:00Z": "Available"}}}}
    )

    merged = merge_campsites([august, september])

    assert len(merged) == 1
    assert set(merged[0].availabilities) == {date(2026, 8, 31), date(2026, 9, 1)}


def test_detects_recreation_rate_limit_errors() -> None:
    assert is_rate_limit_error(Exception("Recreation.gov API returned 429 for https://example.test"))
    assert not is_rate_limit_error(Exception("Recreation.gov API returned 500 for https://example.test"))


def test_recreation_request_context_fetches_json() -> None:
    class Response:
        ok = True
        status = 200

        def json(self):
            return {"campsites": {}}

    class Request:
        def get(self, url, headers):
            self.url = url
            self.headers = headers
            return Response()

    class Context:
        request = Request()

    class Page:
        context = Context()

    assert fetch_json_from_request_context(Page(), "https://example.test") == {"campsites": {}}
    assert Page.context.request.headers["accept"] == "application/json, text/plain, */*"


def test_infers_reserve_california_provider_from_url() -> None:
    search = AppConfig.model_validate(
        {
            "searches": [
                {
                    "name": "reserve-california",
                    "campground": {
                        "name": "ReserveCalifornia Park",
                        "url": "https://www.reservecalifornia.com/park/707/662",
                    },
                    "date_window": {
                        "start": "2026-08-01",
                        "end": "2026-08-31",
                        "nights": 3,
                        "check_in_weekdays": ["Thursday"],
                    },
                }
            ]
        }
    ).searches[0]

    assert infer_provider(search) == Provider.reserve_california


def test_extracts_reserve_california_ids_from_url() -> None:
    assert reserve_california_ids_from_url("https://www.reservecalifornia.com/park/707/662") == ("707", "662")


def test_reserve_california_grid_date_batches_use_reliable_max_size() -> None:
    assert grid_date_batches(date(2026, 8, 1), date(2026, 8, 15)) == [
        (date(2026, 8, 1), date(2026, 8, 15)),
    ]


def test_reserve_california_grid_date_batches_split_after_21_days() -> None:
    assert grid_date_batches(date(2026, 8, 1), date(2026, 8, 31)) == [
        (date(2026, 8, 1), date(2026, 8, 21)),
        (date(2026, 8, 22), date(2026, 8, 31)),
    ]


def test_infers_reserve_california_visible_availability_dates() -> None:
    availability = infer_visible_availabilities(
        "Site 12 Available Thu Aug 6",
        [date(2026, 8, 6), date(2026, 8, 13)],
    )

    assert availability == {date(2026, 8, 6): "Available"}


def test_reserve_california_selected_stay_marks_each_night_available() -> None:
    search = AppConfig.model_validate(
        {
            "searches": [
                {
                    "name": "reserve-california",
                    "campground": {
                        "name": "ReserveCalifornia Park",
                        "url": "https://www.reservecalifornia.com/park/707/662",
                    },
                    "date_window": {
                        "start": "2026-08-01",
                        "end": "2026-08-31",
                        "nights": 3,
                        "check_in_weekdays": ["Thursday"],
                    },
                }
            ]
        }
    ).searches[0]

    assert infer_selected_stay_availabilities(search, date(2026, 8, 6)) == {
        date(2026, 8, 6): "Available",
        date(2026, 8, 7): "Available",
        date(2026, 8, 8): "Available",
    }


def test_parse_reserve_california_grid_campsites() -> None:
    campsites = parse_grid_campsites(
        {
            "Facility": {
                "Units": {
                    "bucket1.44624": {
                        "UnitId": 44624,
                        "Name": "Campsite #100",
                        "ShortName": "100",
                        "VehicleLength": 30,
                        "IsAda": False,
                        "Slices": {
                            "2026-12-03T00:00:00": {
                                "Date": "2026-12-03",
                                "IsFree": True,
                                "IsBlocked": False,
                            },
                            "2026-12-04T00:00:00": {
                                "Date": "2026-12-04",
                                "IsFree": False,
                                "IsBlocked": False,
                            },
                        },
                    }
                }
            }
        }
    )

    assert len(campsites) == 1
    assert campsites[0].campsite_id == "44624"
    assert campsites[0].name == "Campsite #100"
    assert campsites[0].availabilities == {
        date(2026, 12, 3): "Available",
        date(2026, 12, 4): "Unavailable",
    }
