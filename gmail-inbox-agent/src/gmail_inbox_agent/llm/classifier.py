from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from urllib import error, request

from openai import OpenAI

from gmail_inbox_agent.labels import (
    CATEGORY_LABELS,
    IMPORTANT_LABEL,
    LOW_PRIORITY_LABEL,
    NEEDS_ATTENTION_LABEL,
    REVIEWED_LABEL,
    normalize_labels,
)
from gmail_inbox_agent.llm.prompts import SYSTEM_PROMPT
from gmail_inbox_agent.llm.rules import load_rules_text
from gmail_inbox_agent.models import EmailClassification, EmailMessage


class EmailClassifier:
    def __init__(
        self,
        provider: Literal["openai", "ollama"] = "openai",
        api_key: str = "",
        openai_model: str = "gpt-4.1-mini",
        ollama_model: str = "llama3.1:8b",
        ollama_base_url: str = "http://localhost:11434",
        rules_path: Path | None = None,
    ) -> None:
        self.provider = provider
        self.api_key = api_key
        self.openai_model = openai_model
        self.ollama_model = ollama_model
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.rules_text = load_rules_text(rules_path) if rules_path else ""

    def classify(self, message: EmailMessage) -> EmailClassification:
        if self.provider == "ollama":
            return self._classify_with_ollama(message)
        if self.provider == "openai" and self.client:
            return self._classify_with_openai(message)
        return heuristic_classify(message)

    def _classify_with_openai(self, message: EmailMessage) -> EmailClassification:
        if not self.client:
            return heuristic_classify(message)

        prompt = _build_user_prompt(message, self.rules_text)
        response = self.client.responses.create(
            model=self.openai_model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "email_classification",
                    "schema": EmailClassification.model_json_schema(),
                    "strict": True,
                }
            },
        )
        return normalize_classification(EmailClassification.model_validate_json(response.output_text))

    def _classify_with_ollama(self, message: EmailMessage) -> EmailClassification:
        prompt = _build_user_prompt(message, self.rules_text)
        response_json = _post_ollama_generate(
            base_url=self.ollama_base_url,
            payload={
                "model": self.ollama_model,
                "system": SYSTEM_PROMPT,
                "prompt": f"{prompt}\n\nRespond using JSON only.",
                "stream": False,
                "format": EmailClassification.model_json_schema(),
                "options": {"temperature": 0},
            },
        )
        try:
            return normalize_classification(EmailClassification.model_validate_json(response_json["response"]))
        except KeyError as exc:
            raise RuntimeError("Ollama response did not include a response field.") from exc


def heuristic_classify(message: EmailMessage) -> EmailClassification:
    text = " ".join(
        [
            message.subject,
            message.from_email,
            message.snippet,
            message.body_text or "",
        ]
    ).lower()

    category = "other"
    importance = "normal"
    should_archive = False
    should_highlight = False
    labels = [REVIEWED_LABEL]
    reason = "No OpenAI API key configured; used conservative local fallback."

    if any(word in text for word in ["invoice", "bill", "bank", "tax", "payment", "refund"]):
        category = "money"
        importance = "important"
        should_highlight = True
    elif any(word in text for word in ["meeting", "appointment", "calendar", "schedule"]):
        category = "appointment"
        importance = "important"
        should_highlight = True
    elif any(word in text for word in ["interview", "job", "recruiter", "deadline"]):
        category = "work"
        importance = "important"
        should_highlight = True
    elif any(word in text for word in ["receipt", "order confirmation"]):
        category = "receipt"
        importance = "low"
        should_archive = True
    elif any(word in text for word in ["newsletter", "unsubscribe", "sale", "promo", "discount"]):
        category = "newsletter"
        importance = "low"
        should_archive = True

    if category in CATEGORY_LABELS:
        labels.append(CATEGORY_LABELS[category])
    if importance == "important":
        labels.append(IMPORTANT_LABEL)
    if should_highlight:
        labels.append(NEEDS_ATTENTION_LABEL)
    if importance == "low":
        labels.append(LOW_PRIORITY_LABEL)

    return EmailClassification(
        importance=importance,
        category=category,  # type: ignore[arg-type]
        should_archive=should_archive,
        should_highlight=should_highlight,
        labels_to_apply=sorted(set(labels)),
        summary=message.snippet[:220] or message.subject,
        reason=reason,
        confidence=0.55,
    )


def normalize_classification(classification: EmailClassification) -> EmailClassification:
    return classification.model_copy(
        update={"labels_to_apply": normalize_labels([REVIEWED_LABEL, *classification.labels_to_apply])}
    )


def _build_user_prompt(message: EmailMessage, rules_text: str = "") -> str:
    payload = {
        "personal_classification_rules": rules_text or "No personal rules configured.",
        "subject": message.subject,
        "from_email": message.from_email,
        "to_email": message.to_email,
        "date": message.date,
        "snippet": message.snippet,
        "body_text": message.body_text,
        "existing_labels": message.existing_labels,
    }
    return json.dumps(payload, ensure_ascii=True)


def _post_ollama_generate(base_url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise RuntimeError(
            "Ollama request failed. Is Ollama running and is OLLAMA_BASE_URL correct?"
        ) from exc
