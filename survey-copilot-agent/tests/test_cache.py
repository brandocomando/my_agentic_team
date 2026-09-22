from survey_copilot_agent.cache import AnswerCache, answer_cache_key
from survey_copilot_agent.models import AnswerResponse, Choice, Fact, QuestionRequest


def test_answer_cache_returns_copy() -> None:
    cache = AnswerCache(max_size=2)
    cache.set("key", AnswerResponse(answer="yes", choice_ids=["a"], reason="test"))

    cached = cache.get("key")
    assert cached is not None
    cached.choice_ids.append("b")

    assert cache.get("key").choice_ids == ["a"]


def test_answer_cache_key_includes_fact_value() -> None:
    request = QuestionRequest(
        question_text="Pick one",
        input_type="radio",
        choices=[Choice(id="a", label="A")],
    )

    first = answer_cache_key(request, Fact(key="x", value="A", text="A"))
    second = answer_cache_key(request, Fact(key="x", value="B", text="B"))

    assert first != second
