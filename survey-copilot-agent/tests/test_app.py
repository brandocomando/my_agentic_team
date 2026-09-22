from fastapi.testclient import TestClient

from survey_copilot_agent.app import create_app, log_answer, log_learned_answer
from survey_copilot_agent.config import Settings
from survey_copilot_agent.models import AnswerResponse, Choice, Fact, LearnRequest, QuestionRequest


def test_health_endpoint(tmp_path) -> None:
    settings = Settings(db_path=tmp_path / "memory.sqlite")
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_answer_cors_preflight_allows_usertesting_origin(tmp_path) -> None:
    settings = Settings(db_path=tmp_path / "memory.sqlite")
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.options(
            "/answer",
            headers={
                "Origin": "https://app.usertesting.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.usertesting.com"


def test_learned_endpoint_lists_learned_facts(tmp_path) -> None:
    settings = Settings(db_path=tmp_path / "memory.sqlite")
    app = create_app(settings)

    with TestClient(app) as client:
        client.app.state.store.upsert_fact(
            Fact(key="learned_provider_abc123", value="Spectrum", text="Learned text.", source="learned"),
            [1.0],
        )
        response = client.get("/learned")

    assert response.status_code == 200
    assert response.json() == {
        "facts": [
            {
                "key": "learned_provider_abc123",
                "value": "Spectrum",
                "text": "Learned text.",
                "source": "learned",
            }
        ]
    }


def test_delete_learned_endpoint_deletes_only_learned_fact(tmp_path) -> None:
    settings = Settings(db_path=tmp_path / "memory.sqlite")
    app = create_app(settings)

    with TestClient(app) as client:
        client.app.state.store.upsert_fact(
            Fact(key="learned_provider_abc123", value="Spectrum", text="Learned text.", source="learned"),
            [1.0],
        )
        response = client.delete("/learned/learned_provider_abc123")
        learned_response = client.get("/learned")

    assert response.status_code == 200
    assert response.json() == {"key": "learned_provider_abc123", "deleted": True}
    assert learned_response.json() == {"facts": []}


def test_log_answer_uses_info_level(caplog) -> None:
    request = QuestionRequest(
        question_text="Which provider?",
        input_type="radio",
        choices=[Choice(id="spectrum", label="Spectrum")],
    )
    answer = AnswerResponse(
        answer="Spectrum",
        choice_id="spectrum",
        confidence=0.9,
        reason="matched fact:phone_provider",
    )

    with caplog.at_level("INFO", logger="survey_copilot_agent.app"):
        log_answer(request, answer, source="computed")

    assert "answer source=computed" in caplog.text
    assert "answer='Spectrum'" in caplog.text
    assert "question='Which provider?'" in caplog.text


def test_log_learned_answer_uses_info_level(caplog) -> None:
    request = LearnRequest(
        question_text="Which mobile provider?",
        input_type="radio",
        choices=[Choice(id="spectrum", label="Spectrum")],
        answer="Spectrum",
        choice_ids=["spectrum"],
    )
    fact = Fact(
        key="learned_provider_abc123",
        value="Spectrum",
        text="When asked 'Which mobile provider?', the user's answer is 'Spectrum'.",
    )

    with caplog.at_level("INFO", logger="survey_copilot_agent.app"):
        log_learned_answer(request, fact)

    assert "learned answer key='learned_provider_abc123'" in caplog.text
    assert "answer='Spectrum'" in caplog.text
    assert "fact_text=" in caplog.text
