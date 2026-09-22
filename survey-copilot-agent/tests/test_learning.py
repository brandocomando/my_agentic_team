from survey_copilot_agent.learning import fact_from_learn_request
from survey_copilot_agent.models import LearnRequest


def test_fact_from_learn_request_builds_stable_key_and_text() -> None:
    request = LearnRequest(
        question_text="Which mobile provider do you use?",
        input_type="radio",
        answer="AT&T",
    )

    fact = fact_from_learn_request(request)

    assert fact.key.startswith("learned_which_mobile_provider_do_you_use_")
    assert fact.value == "AT&T"
    assert "Which mobile provider do you use?" in fact.text
    assert fact.source == "learned"
