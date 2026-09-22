from survey_copilot_agent.models import Choice, Fact
from survey_copilot_agent.ollama import answer_from_llm_json


def test_answer_from_llm_json_maps_choice_id_to_choice() -> None:
    response = answer_from_llm_json(
        '{"answer":"Within the past 2 weeks","choice_id":"recent","choice_ids":["recent"],"reason":"fact says recent"}',
        [
            Choice(id="recent", label="Within the past 2 weeks"),
            Choice(id="old", label="More than 6 months ago"),
        ],
        confidence=0.76,
        fact="survey",
    )

    assert response.answer == "Within the past 2 weeks"
    assert response.choice_id == "recent"
    assert response.reason == "llm matched fact:survey"


def test_answer_from_llm_json_returns_null_for_empty_choice() -> None:
    response = answer_from_llm_json(
        '{"answer":null,"choice_id":null,"choice_ids":[],"reason":"unsupported"}',
        [Choice(id="recent", label="Within the past 2 weeks")],
        confidence=0.76,
        fact="survey",
    )

    assert response.answer is None
    assert response.reason == "llm fallback returned null for fact:survey"


def test_answer_from_llm_json_rejects_unsupported_choice_when_fact_is_available() -> None:
    response = answer_from_llm_json(
        '{"answer":"AT&T","choice_id":"att","choice_ids":["att"],"reason":"wrong guess"}',
        [
            Choice(id="att", label="AT&T"),
            Choice(id="spectrum", label="Spectrum"),
        ],
        confidence=0.8,
        fact=Fact(
            key="phone_provider",
            value="Spectrum",
            text="The user uses Spectrum for mobile phone service.",
        ),
    )

    assert response.answer is None
    assert response.reason == "llm fallback choice unsupported by fact:phone_provider"
