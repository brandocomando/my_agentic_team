import re

from .models import AnswerResponse, Choice, Fact, QuestionRequest


NUMBER_RE = re.compile(r"\d+")
RANGE_RE = re.compile(r"(\d+)\s*(?:-|to|through)\s*(\d+)", re.IGNORECASE)
OPEN_ENDED_MIN_RE = re.compile(r"(\d+)\s*\+")
RELATIVE_TIME_CHOICES = [
    ("within the past 2 weeks", ["past 2 weeks", "within 2 weeks", "last 2 weeks", "recently"]),
    ("3 to 4 weeks ago", ["3 to 4 weeks", "3-4 weeks", "three to four weeks"]),
    ("1 to 6 months ago", ["1 to 6 months", "1-6 months", "last 6 months"]),
    ("more than 6 months ago", ["more than 6 months", "over 6 months", "longer than 6 months"]),
]


def answer_from_facts(
    request: QuestionRequest,
    facts: list[tuple[Fact, float]],
    min_confidence: float,
) -> AnswerResponse:
    if not facts:
        return AnswerResponse(reason="no relevant facts found")

    fact, score = facts[0]
    if score < min_confidence:
        return AnswerResponse(confidence=score, reason="retrieval confidence below threshold")

    if request.input_type == "checkbox":
        choices = choose_options(request, fact)
        if not choices:
            return AnswerResponse(confidence=score, reason=f"no matching choice found for fact:{fact.key}")
        return AnswerResponse(
            answer=", ".join(choice.label for choice in choices),
            choice_id=choices[0].id,
            choice_ids=[choice.id for choice in choices if choice.id],
            confidence=score,
            reason=f"matched fact:{fact.key}",
        )

    if request.input_type in {"radio", "select"}:
        choice = choose_option(request, fact)
        if choice is None:
            return AnswerResponse(confidence=score, reason=f"no matching choice found for fact:{fact.key}")
        return AnswerResponse(
            answer=choice.label,
            choice_id=choice.id,
            confidence=score,
            reason=f"matched fact:{fact.key}",
        )

    return AnswerResponse(answer=fact.value, confidence=score, reason=f"matched fact:{fact.key}")


def choose_option(request: QuestionRequest, fact: Fact) -> Choice | None:
    choices = choose_options(request, fact)
    if choices:
        return choices[0]

    return None


def choose_options(request: QuestionRequest, fact: Fact) -> list[Choice]:
    normalized_value = normalize(fact.value)
    normalized_fact_text = normalize(f"{fact.value} {fact.text}")
    normalized_support_text = normalized_value if fact.source == "learned" else normalized_fact_text
    value_matched_choices: list[Choice] = []
    text_matched_choices: list[Choice] = []

    for choice in request.choices:
        normalized_label = normalize(choice.label)
        normalized_choice_value = normalize(choice.value)
        if normalized_label and normalized_label != "none of the above" and contains_phrase(normalized_value, normalized_label):
            value_matched_choices.append(choice)
            continue
        if normalized_choice_value and normalized_value and normalized_value == normalized_choice_value:
            value_matched_choices.append(choice)
            continue
        if normalized_value and normalized_value in normalized_label:
            value_matched_choices.append(choice)
            continue
        if normalized_label and normalized_label != "none of the above" and normalized_label in normalized_support_text:
            text_matched_choices.append(choice)
            continue
        if choice_label_supported_by_fact(normalized_label, normalized_support_text):
            text_matched_choices.append(choice)
            continue

    if value_matched_choices:
        return value_matched_choices

    numeric_choice = choose_numeric_range_option(request, fact.value)
    if numeric_choice is not None:
        return [numeric_choice]

    relative_choice = choose_relative_time_option(request, normalized_fact_text)
    if relative_choice is not None:
        return [relative_choice]

    return text_matched_choices


def choose_relative_time_option(request: QuestionRequest, normalized_fact_text: str) -> Choice | None:
    normalized_choices = [(choice, normalize(choice.label)) for choice in request.choices]
    for canonical, fact_phrases in RELATIVE_TIME_CHOICES:
        if not any(phrase in normalized_fact_text for phrase in fact_phrases):
            continue
        for choice, normalized_label in normalized_choices:
            if canonical == normalized_label:
                return choice
    return None


def choose_numeric_range_option(request: QuestionRequest, fact_value: str) -> Choice | None:
    number = parse_int(fact_value)
    if number is None:
        return None

    for choice in request.choices:
        bounds = parse_range(choice.label)
        if bounds is not None and bounds[0] <= number <= bounds[1]:
            return choice

    return None


def choice_label_supported_by_fact(normalized_label: str, normalized_fact_text: str) -> bool:
    if not normalized_label or normalized_label == "none of the above":
        return False
    return contains_phrase(normalized_fact_text, normalized_label)


def contains_phrase(text: str, phrase: str) -> bool:
    escaped = re.escape(normalize(phrase))
    pattern = rf"(^|[^a-z0-9]){escaped}([^a-z0-9]|$)"
    return re.search(pattern, text) is not None


def normalize(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.casefold()).strip()


def parse_int(value: str) -> int | None:
    match = NUMBER_RE.search(value)
    return int(match.group()) if match else None


def parse_range(value: str) -> tuple[int, float] | None:
    match = RANGE_RE.search(value)
    if match:
        return int(match.group(1)), int(match.group(2))

    open_ended_match = OPEN_ENDED_MIN_RE.search(value)
    if open_ended_match:
        return int(open_ended_match.group(1)), float("inf")

    return None
