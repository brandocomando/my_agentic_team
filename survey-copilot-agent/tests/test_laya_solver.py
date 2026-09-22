from unittest.mock import MagicMock

from survey_copilot_agent.laya_solver import LayaSurveySolver
from survey_copilot_agent.models import Choice, Fact, QuestionRequest


def test_laya_solver_radio_choice() -> None:
    mock_router = MagicMock()
    mock_router.predict.return_value = {
        "answers": {
            "selected_option": {
                "choice": "opt_2",
                "confidence": 0.93,
            }
        }
    }
    solver = LayaSurveySolver(router_instance=mock_router, min_confidence=0.70)

    request = QuestionRequest(
        question_text="What is your employment status?",
        input_type="radio",
        choices=[
            Choice(id="opt_1", label="Student"),
            Choice(id="opt_2", label="Employed full-time"),
            Choice(id="opt_3", label="Unemployed"),
        ],
    )
    fact = Fact(key="job", value="Software Engineer", text="I work full-time as a developer.")

    result = solver.choose_answer(request, fact, retrieval_confidence=0.90)

    assert result is not None
    assert result.answer == "Employed full-time"
    assert result.choice_id == "opt_2"
    assert result.confidence == 0.90
    assert "laya:choice matched fact:job" in result.reason
    mock_router.predict.assert_called_once()
    assert mock_router.predict.call_args[1]["model"] == "english"


def test_laya_solver_checkbox_noul() -> None:
    mock_router = MagicMock()
    mock_router.predict.return_value = {
        "answers": {
            "opt_0": {"noul": 0.95},
            "opt_1": {"noul": 0.10},
            "opt_2": {"noul": 0.88},
        }
    }
    solver = LayaSurveySolver(router_instance=mock_router, min_confidence=0.70)

    request = QuestionRequest(
        question_text="Which programming languages do you use?",
        input_type="checkbox",
        choices=[
            Choice(id="c_py", label="Python"),
            Choice(id="c_rb", label="Ruby"),
            Choice(id="c_ts", label="TypeScript"),
        ],
    )
    fact = Fact(
        key="tech_stack",
        value="Python, TypeScript",
        text="Daily driver languages are Python and TS.",
    )

    result = solver.choose_answer(request, fact, retrieval_confidence=0.85)

    assert result is not None
    assert result.choice_ids == ["c_py", "c_ts"]
    assert "Python" in result.answer
    assert "TypeScript" in result.answer
    assert result.confidence == 0.85
    assert "laya:checkbox matched fact:tech_stack" in result.reason


def test_laya_solver_checkbox_calibrated_confidence() -> None:
    mock_router = MagicMock()
    mock_router.predict.return_value = {
        "answers": {
            "opt_0": {"noul": 0.75},
        }
    }
    solver = LayaSurveySolver(router_instance=mock_router, min_confidence=0.70)

    request = QuestionRequest(
        question_text="Do you use Python?",
        input_type="checkbox",
        choices=[Choice(id="c_py", label="Python")],
    )
    fact = Fact(key="tech", value="Python", text="I use Python.")

    # Model probability is 0.75, retrieval is 0.90 -> final confidence should be min(0.90, 0.75) = 0.75
    result = solver.choose_answer(request, fact, retrieval_confidence=0.90)
    assert result is not None
    assert result.confidence == 0.75


def test_laya_solver_checkbox_low_confidence_filtered() -> None:
    mock_router = MagicMock()
    # 0.55 is below min_confidence of 0.70
    mock_router.predict.return_value = {
        "answers": {
            "opt_0": {"noul": 0.55},
        }
    }
    solver = LayaSurveySolver(router_instance=mock_router, min_confidence=0.70)

    request = QuestionRequest(
        question_text="Do you use Python?",
        input_type="checkbox",
        choices=[Choice(id="c_py", label="Python")],
    )
    fact = Fact(key="tech", value="Python", text="Maybe Python.")

    result = solver.choose_answer(request, fact, retrieval_confidence=0.90)
    assert result is None


def test_laya_solver_rejects_over_20_choices() -> None:
    solver = LayaSurveySolver()
    request = QuestionRequest(
        question_text="Pick your favorite number",
        input_type="radio",
        choices=[Choice(id=f"c_{i}", label=str(i)) for i in range(25)],
    )
    fact = Fact(key="num", value="7", text="Lucky number")

    result = solver.choose_answer(request, fact, retrieval_confidence=0.95)
    assert result is None


def test_laya_solver_unsupported_input_type_rejected() -> None:
    solver = LayaSurveySolver()
    request = QuestionRequest(
        question_text="What is your name?",
        input_type="text",
        choices=[Choice(id="c1", label="John")],
    )
    fact = Fact(key="name", value="John", text="User name is John.")

    result = solver.choose_answer(request, fact, retrieval_confidence=0.95)
    assert result is None


def test_laya_solver_low_confidence_filtered() -> None:
    mock_router = MagicMock()
    mock_router.predict.return_value = {
        "answers": {
            "selected_option": {
                "choice": "opt_1",
                "confidence": 0.40,
            }
        }
    }
    solver = LayaSurveySolver(router_instance=mock_router, min_confidence=0.70)

    request = QuestionRequest(
        question_text="Are you a pet owner?",
        input_type="radio",
        choices=[Choice(id="opt_1", label="Yes"), Choice(id="opt_2", label="No")],
    )
    fact = Fact(key="pet", value="Unknown", text="Unclear information")

    result = solver.choose_answer(request, fact, retrieval_confidence=0.80)
    assert result is None


def test_laya_solver_router_exception_returns_none() -> None:
    mock_router = MagicMock()
    mock_router.predict.side_effect = RuntimeError("Inference error")
    solver = LayaSurveySolver(router_instance=mock_router, min_confidence=0.70)

    request = QuestionRequest(
        question_text="What device do you use?",
        input_type="radio",
        choices=[Choice(id="d1", label="MacBook Pro")],
    )
    fact = Fact(key="device", value="MacBook", text="I use a MacBook Pro laptop.")

    result = solver.choose_answer(request, fact, retrieval_confidence=0.88)
    assert result is None


def test_laya_solver_model_name_mapping() -> None:
    mock_router = MagicMock()
    mock_router.predict.return_value = {
        "answers": {
            "selected_option": {"choice": "c1", "confidence": 0.95},
        }
    }
    solver = LayaSurveySolver(
        model_name="convaiinnovations/laya-typed-decisions",
        router_instance=mock_router,
        min_confidence=0.70,
    )

    request = QuestionRequest(
        question_text="Decision question",
        input_type="radio",
        choices=[Choice(id="c1", label="Option A")],
    )
    fact = Fact(key="k", value="v", text="t")

    solver.choose_answer(request, fact, retrieval_confidence=0.90)
    assert mock_router.predict.call_args[1]["model"] == "typed-decisions"


def test_laya_solver_heuristic_fallback() -> None:
    solver = LayaSurveySolver(router_instance=None)
    solver._ensure_router = lambda: None

    request = QuestionRequest(
        question_text="What device do you use?",
        input_type="radio",
        choices=[
            Choice(id="d1", label="MacBook Pro"),
            Choice(id="d2", label="Windows Desktop"),
        ],
    )
    fact = Fact(key="device", value="MacBook", text="I use a MacBook Pro laptop.")

    result = solver.choose_answer(request, fact, retrieval_confidence=0.88)
    assert result is not None
    assert result.answer == "MacBook Pro"
    assert result.choice_id == "d1"


def test_laya_solver_heuristic_fallback_low_confidence() -> None:
    solver = LayaSurveySolver(router_instance=None, min_confidence=0.70)
    solver._ensure_router = lambda: None

    request = QuestionRequest(
        question_text="What device do you use?",
        input_type="radio",
        choices=[Choice(id="d1", label="MacBook Pro")],
    )
    fact = Fact(key="device", value="MacBook", text="I use a MacBook Pro laptop.")

    # 0.60 is below 0.70 min_confidence
    result = solver.choose_answer(request, fact, retrieval_confidence=0.60)
    assert result is None


def test_laya_solver_warmup() -> None:
    mock_router = MagicMock()
    solver = LayaSurveySolver(router_instance=mock_router)
    solver.warmup()
    assert solver._ensure_router() is mock_router
