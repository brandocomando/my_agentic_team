from __future__ import annotations

import json
from datetime import date
from urllib.error import HTTPError

from campsite_finder_agent.ai import AI_MATCH_BATCH_SIZE, analyze_match_windows_with_ollama, match_payload, render_ai_summary, request_ollama_analysis
from campsite_finder_agent.models import AIPreferences, MatchWindow


def make_match_window(state_key: str = "state-1") -> MatchWindow:
    return MatchWindow(
        state_key=state_key,
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


def test_analyze_match_windows_scores_large_batches_in_chunks(monkeypatch) -> None:
    requested_batch_sizes = []

    class Response:
        def __init__(self, state_keys):
            self.state_keys = state_keys

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
                                "summary": "Batch scored.",
                                "matches": [
                                    {
                                        "state_key": state_key,
                                        "score": 8.0,
                                        "fit": "strong",
                                        "reasons": ["chunked"],
                                        "concerns": [],
                                        "summary": "Good fit.",
                                        "suggested_state_action": "watch",
                                        "suggested_state_reason": "Strong enough to watch.",
                                    }
                                    for state_key in self.state_keys
                                ],
                            }
                        )
                    }
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        user_payload = json.loads(payload["messages"][1]["content"])
        state_keys = [item["state_key"] for item in user_payload["matches"]]
        requested_batch_sizes.append(len(state_keys))
        return Response(state_keys)

    monkeypatch.setattr("campsite_finder_agent.ai.urlopen", fake_urlopen)
    matches = [make_match_window(f"state-{index}") for index in range(AI_MATCH_BATCH_SIZE + 2)]

    summary = analyze_match_windows_with_ollama(
        matches,
        {"beach-local-rv-thu-sun": AIPreferences(likes=["coastal"])},
        model="llama3.1",
        base_url="http://localhost:11434",
    )

    assert requested_batch_sizes == [AI_MATCH_BATCH_SIZE, 2]
    assert "Batch scored." in summary
    assert all(match.ai_score == 8.0 for match in matches)


def test_analyze_match_windows_retries_missing_scores(monkeypatch) -> None:
    requested_batches = []

    class Response:
        def __init__(self, state_keys):
            self.state_keys = state_keys

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
                                "summary": "Scored available keys.",
                                "matches": [
                                    {
                                        "state_key": state_key,
                                        "score": 8.0,
                                        "fit": "strong",
                                        "reasons": ["retried"],
                                        "concerns": [],
                                        "summary": "Good fit.",
                                        "suggested_state_action": "watch",
                                        "suggested_state_reason": "Worth watching.",
                                    }
                                    for state_key in self.state_keys
                                ],
                            }
                        )
                    }
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        user_payload = json.loads(payload["messages"][1]["content"])
        state_keys = [item["state_key"] for item in user_payload["matches"]]
        requested_batches.append(state_keys)
        if len(state_keys) > 1:
            state_keys = state_keys[:-1]
        return Response(state_keys)

    monkeypatch.setattr("campsite_finder_agent.ai.urlopen", fake_urlopen)
    matches = [make_match_window(f"state-{index}") for index in range(3)]

    analyze_match_windows_with_ollama(
        matches,
        {"beach-local-rv-thu-sun": AIPreferences(likes=["coastal"])},
        model="llama3.1",
        base_url="http://localhost:11434",
    )

    assert requested_batches == [["state-0", "state-1", "state-2"], ["state-2"]]
    assert all(match.ai_score == 8.0 for match in matches)


def test_analyze_match_windows_keeps_partial_scores_when_retry_still_skips(monkeypatch) -> None:
    class Response:
        def __init__(self, state_keys):
            self.state_keys = state_keys

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
                                "summary": "Partial score.",
                                "matches": [
                                    {
                                        "state_key": state_key,
                                        "score": 8.0,
                                        "fit": "strong",
                                        "reasons": ["partial"],
                                        "concerns": [],
                                        "summary": "Good fit.",
                                        "suggested_state_action": "watch",
                                        "suggested_state_reason": "Worth watching.",
                                    }
                                    for state_key in self.state_keys
                                    if state_key != "state-2"
                                ],
                            }
                        )
                    }
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        user_payload = json.loads(payload["messages"][1]["content"])
        return Response([item["state_key"] for item in user_payload["matches"]])

    monkeypatch.setattr("campsite_finder_agent.ai.urlopen", fake_urlopen)
    matches = [make_match_window(f"state-{index}") for index in range(3)]

    summary = analyze_match_windows_with_ollama(
        matches,
        {"beach-local-rv-thu-sun": AIPreferences(likes=["coastal"])},
        model="llama3.1",
        base_url="http://localhost:11434",
    )

    assert matches[0].ai_score == 8.0
    assert matches[1].ai_score == 8.0
    assert matches[2].ai_score is None
    assert "Ollama skipped 1 match(es): state-2" in summary


def test_ollama_analysis_falls_back_to_generate_when_chat_is_missing(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(
                {
                    "response": json.dumps(
                        {
                            "summary": "Generate endpoint scored the match.",
                            "matches": [
                                {
                                    "state_key": "state-1",
                                    "score": 8.1,
                                    "fit": "strong",
                                    "reasons": ["fallback worked"],
                                    "concerns": [],
                                    "summary": "Worth watching.",
                                    "suggested_state_action": "watch",
                                    "suggested_state_reason": "Good enough to keep visible.",
                                }
                            ],
                        }
                    )
                }
            ).encode("utf-8")

    requested_urls = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        if request.full_url.endswith("/api/chat"):
            raise HTTPError(request.full_url, 404, "Not Found", hdrs=None, fp=None)
        return Response()

    monkeypatch.setattr("campsite_finder_agent.ai.urlopen", fake_urlopen)

    response = request_ollama_analysis(
        [make_match_window()],
        {"beach-local-rv-thu-sun": AIPreferences(likes=["coastal"])},
        model="llama3.1",
        base_url="http://localhost:11434",
    )

    assert requested_urls == ["http://localhost:11434/api/chat", "http://localhost:11434/api/generate"]
    assert response.matches[0].score == 8.1


def test_ollama_analysis_requires_a_score_for_each_match(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps({"message": {"content": json.dumps({"summary": "No matches.", "matches": []})}}).encode(
                "utf-8"
            )

    monkeypatch.setattr("campsite_finder_agent.ai.urlopen", lambda request, timeout: Response())

    try:
        request_ollama_analysis(
            [make_match_window()],
            {"beach-local-rv-thu-sun": AIPreferences(likes=["coastal"])},
            model="llama3.1",
            base_url="http://localhost:11434",
        )
    except RuntimeError as exc:
        assert "Ollama did not score 1 match" in str(exc)
    else:
        raise AssertionError("Expected missing Ollama score to raise")


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
