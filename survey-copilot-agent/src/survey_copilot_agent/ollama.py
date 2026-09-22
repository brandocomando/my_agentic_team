import json

import httpx

from .answering import choice_label_supported_by_fact, normalize
from .models import AnswerResponse, Choice, Fact, QuestionRequest


class OllamaClient:
    def __init__(self, base_url: str, chat_model: str, embed_model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.embed_model = embed_model

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.embed_model, "prompt": text},
            )
            response.raise_for_status()
        data = response.json()
        embedding = data.get("embedding")
        if not isinstance(embedding, list):
            raise ValueError("Ollama embedding response did not include an embedding list")
        return [float(value) for value in embedding]

    async def choose_answer(
        self,
        request: QuestionRequest,
        fact: Fact,
        confidence: float,
    ) -> AnswerResponse:
        prompt = build_choice_prompt(request, fact)
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.chat_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You answer survey questions using only the supplied fact. "
                                "Return strict JSON only. If the fact does not support an answer, return null."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": "json",
                },
            )
            response.raise_for_status()

        content = response.json().get("message", {}).get("content", "{}")
        return answer_from_llm_json(content, request.choices, confidence, fact)


def build_choice_prompt(request: QuestionRequest, fact: Fact) -> str:
    choices = [
        {"id": choice.id, "label": choice.label, "value": choice.value}
        for choice in request.choices
    ]
    return json.dumps(
        {
            "question_text": request.question_text,
            "input_type": request.input_type,
            "choices": choices,
            "fact": {
                "key": fact.key,
                "value": fact.value,
                "text": fact.text,
            },
            "instructions": (
                "Choose only from the provided choices. For radio/select choose one choice_id. "
                "For checkbox choose zero or more choice_ids. Return JSON with keys answer, choice_id, choice_ids, reason. "
                "Use null answer and empty choice_ids if unsupported."
            ),
        },
        ensure_ascii=True,
    )


def answer_from_llm_json(
    content: str,
    choices: list[Choice],
    confidence: float,
    fact: Fact | str,
) -> AnswerResponse:
    fact_key = fact.key if isinstance(fact, Fact) else fact
    normalized_fact_text = normalize(f"{fact.value} {fact.text}") if isinstance(fact, Fact) else ""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return AnswerResponse(confidence=confidence, reason=f"llm fallback returned invalid json for fact:{fact_key}")

    selected_ids = normalize_choice_ids(data.get("choice_ids"))
    selected_id = data.get("choice_id")
    if selected_id and selected_id not in selected_ids:
        selected_ids.insert(0, str(selected_id))

    selected_choices = [choice for choice in choices if choice.id in selected_ids or choice.value in selected_ids]
    if not selected_choices and isinstance(data.get("answer"), str):
        answer = data["answer"].strip()
        selected_choices = [choice for choice in choices if choice.label == answer]

    if not selected_choices:
        return AnswerResponse(confidence=confidence, reason=f"llm fallback returned null for fact:{fact_key}")

    if normalized_fact_text:
        supported_choices = [
            choice
            for choice in selected_choices
            if choice_label_supported_by_fact(normalize(choice.label), normalized_fact_text)
        ]
        if supported_choices:
            selected_choices = supported_choices
        elif len(selected_choices) == 1 and normalize(selected_choices[0].label) != "none of the above":
            return AnswerResponse(
                confidence=confidence,
                reason=f"llm fallback choice unsupported by fact:{fact_key}",
            )

    return AnswerResponse(
        answer=", ".join(choice.label for choice in selected_choices),
        choice_id=selected_choices[0].id,
        choice_ids=[choice.id for choice in selected_choices if choice.id],
        confidence=confidence,
        reason=f"llm matched fact:{fact_key}",
    )


def normalize_choice_ids(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]
