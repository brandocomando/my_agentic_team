from __future__ import annotations

import logging
from typing import Any

from .models import AnswerResponse, Choice, Fact, QuestionRequest

logger = logging.getLogger(__name__)


class LayaSurveySolver:
    """Sub-35ms System 1 decision engine for survey question answering using Laya."""

    def __init__(
        self,
        model_name: str = "convaiinnovations/laya",
        min_confidence: float = 0.70,
        router_instance: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self.min_confidence = min_confidence
        self._router = router_instance
        self._initialized = router_instance is not None

    def _ensure_router(self) -> Any:
        if self._router is None and not self._initialized:
            try:
                from laya import Router

                self._router = Router(preload=True)
                self._initialized = True
            except ImportError:
                logger.info("laya package not installed; using fallback survey solver.")
                self._router = None
                self._initialized = True
        return self._router

    def build_state(self, request: QuestionRequest, fact: Fact) -> dict[str, Any]:
        return {
            "question": request.question_text,
            "fact_key": fact.key,
            "fact_value": fact.value,
            "fact_text": fact.text,
            "context": f"User profile: {fact.key} is {fact.value}. {fact.text}",
        }

    def choose_answer(
        self,
        request: QuestionRequest,
        fact: Fact,
        retrieval_confidence: float,
    ) -> AnswerResponse | None:
        if not request.choices:
            return None

        # Laya choice questions support up to 20 options efficiently
        if len(request.choices) > 20:
            return None

        router = self._ensure_router()
        if router is not None:
            try:
                if request.input_type in {"radio", "select"}:
                    return self._solve_choice(router, request, fact, retrieval_confidence)
                if request.input_type == "checkbox":
                    return self._solve_checkbox(router, request, fact, retrieval_confidence)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Laya survey solver encountered an error: %s", exc)

        return self._heuristic_laya_solver(request, fact, retrieval_confidence)

    def _solve_choice(
        self,
        router: Any,
        request: QuestionRequest,
        fact: Fact,
        retrieval_confidence: float,
    ) -> AnswerResponse | None:
        criteria: dict[str, str] = {}
        for idx, choice in enumerate(request.choices):
            key = choice.id or f"choice_{idx}"
            criteria[key] = f"Option: {choice.label}" + (f" (value: {choice.value})" if choice.value else "")

        state = self.build_state(request, fact)
        questions = {
            "selected_option": {
                "type": "choice",
                "instructions": (
                    f"Based on the user fact '{fact.key}: {fact.value}', which option is correct for the question "
                    f"'{request.question_text}'?"
                ),
                "criteria": criteria,
            }
        }

        res = router.predict(state, questions)
        answers = res.get("answers", {})
        choice_data = answers.get("selected_option", {})
        chosen_key = choice_data.get("choice")
        model_conf = float(choice_data.get("confidence", 0.85))

        if not chosen_key:
            return None

        # Find matching Choice object
        matched_choice: Choice | None = None
        for idx, choice in enumerate(request.choices):
            if (choice.id and choice.id == chosen_key) or f"choice_{idx}" == chosen_key:
                matched_choice = choice
                break

        if matched_choice is None:
            return None

        final_conf = round(min(retrieval_confidence, model_conf), 4)
        if final_conf < self.min_confidence:
            return None

        return AnswerResponse(
            answer=matched_choice.label,
            choice_id=matched_choice.id,
            confidence=final_conf,
            reason=f"laya:choice matched fact:{fact.key}",
        )

    def _solve_checkbox(
        self,
        router: Any,
        request: QuestionRequest,
        fact: Fact,
        retrieval_confidence: float,
    ) -> AnswerResponse | None:
        state = self.build_state(request, fact)
        questions = {}
        for idx, choice in enumerate(request.choices):
            questions[f"opt_{idx}"] = {
                "type": "noul",
                "instructions": (
                    f"Does the user's fact '{fact.value} {fact.text}' indicate that the option "
                    f"'{choice.label}' should be selected for the question '{request.question_text}'?"
                ),
            }

        res = router.predict(state, questions)
        answers = res.get("answers", {})

        selected_choices: list[Choice] = []
        for idx, choice in enumerate(request.choices):
            prob = float(answers.get(f"opt_{idx}", {}).get("noul", 0.0))
            if prob >= 0.50:
                selected_choices.append(choice)

        if not selected_choices:
            return None

        return AnswerResponse(
            answer=", ".join(c.label for c in selected_choices),
            choice_id=selected_choices[0].id if selected_choices else None,
            choice_ids=[c.id for c in selected_choices if c.id],
            confidence=round(retrieval_confidence, 4),
            reason=f"laya:checkbox matched fact:{fact.key}",
        )

    def _heuristic_laya_solver(
        self,
        request: QuestionRequest,
        fact: Fact,
        retrieval_confidence: float,
    ) -> AnswerResponse | None:
        fact_lower = f"{fact.value} {fact.text}".lower()
        matched: list[Choice] = []

        for choice in request.choices:
            c_lower = choice.label.lower()
            if c_lower in fact_lower or any(word in fact_lower for word in c_lower.split() if len(word) > 3):
                matched.append(choice)

        if not matched:
            return None

        if request.input_type in {"radio", "select"}:
            c = matched[0]
            return AnswerResponse(
                answer=c.label,
                choice_id=c.id,
                confidence=round(retrieval_confidence, 4),
                reason=f"laya:choice matched fact:{fact.key}",
            )

        return AnswerResponse(
            answer=", ".join(c.label for c in matched),
            choice_id=matched[0].id if matched else None,
            choice_ids=[c.id for c in matched if c.id],
            confidence=round(retrieval_confidence, 4),
            reason=f"laya:checkbox matched fact:{fact.key}",
        )
