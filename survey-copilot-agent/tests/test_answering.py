from survey_copilot_agent.answering import answer_from_facts, choose_option
from survey_copilot_agent.models import Choice, Fact, QuestionRequest


def test_age_range_selects_matching_radio_choice() -> None:
    request = QuestionRequest(
        question_text="What age range do you fall into?",
        input_type="radio",
        choices=[
            Choice(id="a", label="18-24"),
            Choice(id="b", label="35-44"),
        ],
    )
    fact = Fact(key="age", value="36", text="The user is 36 years old.")

    choice = choose_option(request, fact)

    assert choice is not None
    assert choice.id == "b"


def test_numeric_profile_fact_selects_matching_radio_range() -> None:
    request = QuestionRequest(
        question_text="How many employees are in your organization?",
        input_type="radio",
        choices=[
            Choice(id="small", label="251-500"),
            Choice(id="medium", label="501-1000"),
            Choice(id="large", label="1001-5000"),
            Choice(id="enterprise", label="5000+"),
        ],
    )
    fact = Fact(
        key="employees",
        value="900",
        text="The user's employer has 900 employees.",
    )

    response = answer_from_facts(request, [(fact, 0.95)], min_confidence=0.62)

    assert response.choice_id == "medium"
    assert response.answer == "501-1000"


def test_numeric_profile_fact_selects_open_ended_radio_range() -> None:
    request = QuestionRequest(
        question_text="How many employees are in your organization?",
        input_type="radio",
        choices=[
            Choice(id="large", label="1001-5000"),
            Choice(id="enterprise", label="5000+"),
        ],
    )
    fact = Fact(
        key="employees",
        value="7500",
        text="The user's employer has 7500 employees.",
    )

    response = answer_from_facts(request, [(fact, 0.95)], min_confidence=0.62)

    assert response.choice_id == "enterprise"
    assert response.answer == "5000+"


def test_exact_age_text_answer_returns_fact_value() -> None:
    request = QuestionRequest(question_text="What is your exact age?", input_type="text")
    fact = Fact(key="age", value="36", text="The user is 36 years old.")

    response = answer_from_facts(request, [(fact, 0.91)], min_confidence=0.62)

    assert response.answer == "36"
    assert response.confidence == 0.91


def test_low_confidence_returns_null_answer() -> None:
    request = QuestionRequest(question_text="What is your exact age?", input_type="text")
    fact = Fact(key="age", value="36", text="The user is 36 years old.")

    response = answer_from_facts(request, [(fact, 0.2)], min_confidence=0.62)

    assert response.answer is None
    assert response.reason == "retrieval confidence below threshold"


def test_checkbox_can_match_multiple_values_inside_one_fact() -> None:
    request = QuestionRequest(
        question_text="Which financial institutions do you use?",
        input_type="checkbox",
        choices=[
            Choice(id="chase", label="Chase"),
            Choice(id="boa", label="Bank of America"),
            Choice(id="none", label="None of the Above"),
        ],
    )
    fact = Fact(
        key="financial_institutions",
        value="Chase, Bank of America",
        text="The user banks with Chase and Bank of America.",
    )

    response = answer_from_facts(request, [(fact, 0.9)], min_confidence=0.62)

    assert response.choice_ids == ["chase", "boa"]
    assert response.answer == "Chase, Bank of America"


def test_relative_time_choice_matches_without_llm() -> None:
    request = QuestionRequest(
        question_text="When did you last take a survey?",
        input_type="radio",
        choices=[
            Choice(id="two_weeks", label="Within the past 2 weeks"),
            Choice(id="month", label="3 to 4 weeks ago"),
            Choice(id="six_months", label="1 to 6 months ago"),
            Choice(id="old", label="More than 6 months ago"),
        ],
    )
    fact = Fact(
        key="survey",
        value="recently",
        text="The user took a survey within the past 2 weeks.",
    )

    response = answer_from_facts(request, [(fact, 0.9)], min_confidence=0.62)

    assert response.choice_id == "two_weeks"
    assert response.reason == "matched fact:survey"


def test_direct_provider_fact_matches_supported_choice() -> None:
    request = QuestionRequest(
        question_text="Which mobile provider do you use?",
        input_type="radio",
        choices=[
            Choice(id="att", label="AT&T"),
            Choice(id="spectrum", label="Spectrum"),
            Choice(id="boost", label="Boost Mobile"),
        ],
    )
    fact = Fact(
        key="phone_provider",
        value="Spectrum",
        text="The user uses Spectrum for mobile phone service.",
    )

    response = answer_from_facts(request, [(fact, 0.95)], min_confidence=0.62)

    assert response.choice_id == "spectrum"
    assert response.answer == "Spectrum"


def test_learned_radio_answer_value_wins_over_choice_labels_in_question_text() -> None:
    request = QuestionRequest(
        question_text="Google Pixel Watch Fitbit Halo Fossil",
        input_type="radio",
        choices=[
            Choice(id="pixel", label="Google Pixel Watch"),
            Choice(id="fitbit", label="Fitbit"),
            Choice(id="halo", label="Halo"),
            Choice(id="fossil", label="Fossil"),
        ],
    )
    fact = Fact(
        key="learned_google_pixel_watch_fitbit_halo_fossil",
        value="Fitbit",
        text=(
            "When asked 'Google Pixel Watch Fitbit Halo Fossil', "
            "the user's answer is 'Fitbit'."
        ),
        source="learned",
    )

    response = answer_from_facts(request, [(fact, 0.95)], min_confidence=0.62)

    assert response.choice_id == "fitbit"
    assert response.answer == "Fitbit"
