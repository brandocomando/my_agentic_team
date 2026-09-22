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


def test_answer_endpoint_laya_success(tmp_path) -> None:
    from unittest.mock import AsyncMock, MagicMock

    mock_ollama = MagicMock()
    mock_ollama.embed = AsyncMock(return_value=[1.0, 0.0])
    mock_ollama.choose_answer = AsyncMock()

    mock_laya = MagicMock()
    mock_laya.choose_answer.return_value = AnswerResponse(
        answer="Employed full-time",
        choice_id="opt_2",
        confidence=0.90,
        reason="laya:choice matched fact:job",
    )

    settings = Settings(db_path=tmp_path / "memory.sqlite", use_laya=True)
    app = create_app(settings, ollama=mock_ollama, laya_solver=mock_laya)

    with TestClient(app) as client:
        client.app.state.store.upsert_fact(
            Fact(key="job", value="Software Engineer", text="I work full-time.", source="profile"),
            [1.0, 0.0],
        )

        response = client.post(
            "/answer",
            json={
                "question_text": "What is your employment status?",
                "input_type": "radio",
                "choices": [
                    {"id": "opt_1", "label": "Student"},
                    {"id": "opt_2", "label": "Employed full-time"},
                ],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Employed full-time"
    assert data["choice_id"] == "opt_2"
    assert data["confidence"] == 0.90
    assert "laya:choice" in data["reason"]
    mock_ollama.choose_answer.assert_not_called()


def test_answer_endpoint_laya_none_falls_back_to_ollama(tmp_path) -> None:
    from unittest.mock import AsyncMock, MagicMock

    mock_ollama = MagicMock()
    mock_ollama.embed = AsyncMock(return_value=[1.0, 0.0])
    mock_ollama.choose_answer = AsyncMock(
        return_value=AnswerResponse(
            answer="Employed full-time",
            choice_id="opt_2",
            confidence=0.88,
            reason="ollama:reasoning matched fact:job",
        )
    )

    mock_laya = MagicMock()
    mock_laya.choose_answer.return_value = None  # Laya cannot resolve

    settings = Settings(db_path=tmp_path / "memory.sqlite", use_laya=True)
    app = create_app(settings, ollama=mock_ollama, laya_solver=mock_laya)

    with TestClient(app) as client:
        client.app.state.store.upsert_fact(
            Fact(key="job", value="Software Engineer", text="I work full-time.", source="profile"),
            [1.0, 0.0],
        )

        response = client.post(
            "/answer",
            json={
                "question_text": "What is your employment status?",
                "input_type": "radio",
                "choices": [
                    {"id": "opt_1", "label": "Student"},
                    {"id": "opt_2", "label": "Employed full-time"},
                ],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Employed full-time"
    assert "ollama:reasoning" in data["reason"]
    mock_ollama.choose_answer.assert_called_once()


def test_answer_endpoint_use_laya_disabled(tmp_path) -> None:
    from unittest.mock import AsyncMock, MagicMock

    mock_ollama = MagicMock()
    mock_ollama.embed = AsyncMock(return_value=[1.0, 0.0])
    mock_ollama.choose_answer = AsyncMock(
        return_value=AnswerResponse(
            answer="Employed full-time",
            choice_id="opt_2",
            confidence=0.88,
            reason="ollama:reasoning matched fact:job",
        )
    )

    mock_laya = MagicMock()

    settings = Settings(db_path=tmp_path / "memory.sqlite", use_laya=False)
    app = create_app(settings, ollama=mock_ollama, laya_solver=mock_laya)

    with TestClient(app) as client:
        client.app.state.store.upsert_fact(
            Fact(key="job", value="Software Engineer", text="I work full-time.", source="profile"),
            [1.0, 0.0],
        )

        response = client.post(
            "/answer",
            json={
                "question_text": "What is your employment status?",
                "input_type": "radio",
                "choices": [
                    {"id": "opt_1", "label": "Student"},
                    {"id": "opt_2", "label": "Employed full-time"},
                ],
            },
        )

    assert response.status_code == 200
    mock_laya.choose_answer.assert_not_called()
    mock_ollama.choose_answer.assert_called_once()


def test_answer_endpoint_laya_error_falls_back_to_ollama(tmp_path) -> None:
    from unittest.mock import AsyncMock, MagicMock

    mock_ollama = MagicMock()
    mock_ollama.embed = AsyncMock(return_value=[1.0, 0.0])
    mock_ollama.choose_answer = AsyncMock(
        return_value=AnswerResponse(
            answer="Employed full-time",
            choice_id="opt_2",
            confidence=0.85,
            reason="ollama:fallback",
        )
    )

    mock_laya = MagicMock()
    mock_laya.choose_answer.side_effect = RuntimeError("Laya engine failed")

    settings = Settings(db_path=tmp_path / "memory.sqlite", use_laya=True)
    app = create_app(settings, ollama=mock_ollama, laya_solver=mock_laya)

    with TestClient(app) as client:
        client.app.state.store.upsert_fact(
            Fact(key="job", value="Software Engineer", text="I work full-time.", source="profile"),
            [1.0, 0.0],
        )

        response = client.post(
            "/answer",
            json={
                "question_text": "What is your employment status?",
                "input_type": "radio",
                "choices": [
                    {"id": "opt_1", "label": "Student"},
                    {"id": "opt_2", "label": "Employed full-time"},
                ],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Employed full-time"
    assert "ollama:fallback" in data["reason"]
    mock_ollama.choose_answer.assert_called_once()


def test_answer_endpoint_cache_behavior(tmp_path) -> None:
    from unittest.mock import AsyncMock, MagicMock

    mock_ollama = MagicMock()
    mock_ollama.embed = AsyncMock(return_value=[1.0, 0.0])
    mock_ollama.choose_answer = AsyncMock()

    mock_laya = MagicMock()
    mock_laya.choose_answer.return_value = AnswerResponse(
        answer="Employed full-time",
        choice_id="opt_2",
        confidence=0.90,
        reason="laya:choice matched fact:job",
    )

    settings = Settings(db_path=tmp_path / "memory.sqlite", use_laya=True)
    app = create_app(settings, ollama=mock_ollama, laya_solver=mock_laya)

    with TestClient(app) as client:
        client.app.state.store.upsert_fact(
            Fact(key="job", value="Software Engineer", text="I work full-time.", source="profile"),
            [1.0, 0.0],
        )

        payload = {
            "question_text": "What is your employment status?",
            "input_type": "radio",
            "choices": [
                {"id": "opt_1", "label": "Student"},
                {"id": "opt_2", "label": "Employed full-time"},
            ],
        }
        res1 = client.post("/answer", json=payload)
        assert res1.status_code == 200
        assert mock_laya.choose_answer.call_count == 1

        # Second call should hit the in-memory cache
        res2 = client.post("/answer", json=payload)
        assert res2.status_code == 200
        assert res2.json()["answer"] == "Employed full-time"
        assert mock_laya.choose_answer.call_count == 1

