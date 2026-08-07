from __future__ import annotations

from datetime import date

import pytest

from campsite_finder_agent.recreation import _normalize_recreation_equipment, poll_recreation_site_availability


class Response:
    ok = True

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def json(self) -> dict:
        return self.payload


class Request:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def get(self, url: str, headers: dict[str, str]):
        return Response(self.payload)


class Context:
    def __init__(self, payload: dict) -> None:
        self.request = Request(payload)


class Page:
    def __init__(self, payload: dict) -> None:
        self.context = Context(payload)


def recreation_payload(status: str) -> dict:
    return {
        "campsites": {
            "64036": {
                "campsite_id": "64036",
                "site": "118",
                "availabilities": {
                    "2027-03-20T00:00:00Z": status,
                    "2027-03-21T00:00:00Z": status,
                },
            }
        }
    }


def test_recreation_get_site_treats_nyr_as_not_available() -> None:
    result = poll_recreation_site_availability(Page(recreation_payload("NYR")), "232250", "118", date(2027, 3, 20), 2)

    assert result["action"] == "not-available"
    assert [state["status"] for state in result["states"]] == ["NYR", "NYR"]


def test_recreation_get_site_detects_available_stay() -> None:
    result = poll_recreation_site_availability(Page(recreation_payload("Available")), "232250", "118", date(2027, 3, 20), 2)

    assert result["action"] == "available"
    assert result["campsite_id"] == "64036"
    assert result["campsite_name"] == "118"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Trailer", "trailer"),
        ("travel trailer", "trailer"),
        ("Pickup Camper", "pickup_camper"),
        ("pop up", "pop_up"),
        ("5th wheel", "fifth_wheel"),
    ],
)
def test_recreation_equipment_normalization(value: str, expected: str) -> None:
    assert _normalize_recreation_equipment(value) == expected
