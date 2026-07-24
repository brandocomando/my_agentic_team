from __future__ import annotations

import json
from datetime import date

from campsite_finder_agent.ai import analyze_match_windows_with_ollama, match_payload, render_ai_summary
from campsite_finder_agent.models import AIPreferences, MatchWindow


def make_match_window() -> MatchWindow:
    return MatchWindow(
        state_key="state-1",
        search_names=["beach-local-rv-thu-sun-san-elijo"],
        campground_id="ReserveCalifornia:709",
        campground_name="San Elijo State Beach",
        campground_url="https://outdoorithm.com/campgrounds/ca/san-elijo-sb/san-elijo-state-beach",
        check_in_window_start=date(2026, 8, 6),
        check_in_window_end=date(2026, 8, 6),
        earliest_check_out=date(2026, 8, 9),
        latest_check_out=date(2026, 8, 9),
        nights=3,
        representative_campsite_id="101",
        representative_campsite_name="Site 101",
        representative_site_type="STANDARD",
        representative_loop="Beach Loop",
        matching_campsite_ids=["101"],
        matching_start_count=1,
        unique_site_count=1,
    )


def test_match_payload_contains_review_fields() -> None:
    payload = match_payload(make_match_window())

    assert payload["state_key"] == "state-1"
    assert payload["campground_id"] == "ReserveCalifornia:709"
    assert payload["campground_name"] == "San Elijo State Beach"
    assert payload["nights"] == 3


def test_analyze_match_windows_with_ollama_enriches_matches(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "San Elijo is the strongest match.",
                                "matches": [
                                    {
                                        "state_key": "state-1",
                                        "score": 9.2,
                                        "fit": "excellent",
                                        "reasons": ["coastal", "Thursday window"],
                                        "concerns": ["popular campground"],
                                        "summary": "Book-worthy beach RV option.",
                                        "suggested_state_action": "book",
                                        "suggested_state_reason": "Matches key preferences.",
                                    }
                                ],
                            }
                        )
                    }
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        assert timeout == 45
        return Response()

    monkeypatch.setattr("campsite_finder_agent.ai.urlopen", fake_urlopen)
    match = make_match_window()

    summary = analyze_match_windows_with_ollama(
        [match],
        {"beach-local-rv-thu-sun": AIPreferences(likes=["coastal"], dislikes=["primitive"])},
        model="llama3.1",
        base_url="http://localhost:11434",
    )

    assert "San Elijo is the strongest match." in summary
    assert match.ai_score == 9.2
    assert match.ai_fit == "excellent"
    assert match.ai_reasons == ["coastal", "Thursday window"]
    assert match.ai_concerns == ["popular campground"]
    assert match.suggested_state_action == "book"
    assert match.suggested_state_reason == "Matches key preferences."


def test_render_ai_summary_orders_by_score() -> None:
    matches = [make_match_window()]
    response = type(
        "Response",
        (),
        {
            "summary": "One strong option.",
            "matches": [
                type(
                    "Analysis",
                    (),
                    {
                        "state_key": "state-1",
                        "score": 8.5,
                        "fit": "strong",
                        "summary": "Good fit.",
                        "suggested_state_action": "watch",
                        "suggested_state_reason": "Worth monitoring.",
                    },
                )()
            ],
        },
    )()

    summary = render_ai_summary(response, matches)

    assert "AI campsite review" in summary
    assert "San Elijo State Beach: 8.5/10 strong" in summary
    assert "Suggested state: watch - Worth monitoring." in summary
