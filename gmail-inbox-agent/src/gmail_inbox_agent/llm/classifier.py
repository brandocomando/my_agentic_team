from __future__ import annotations

import json

from openai import OpenAI

from gmail_inbox_agent.llm.prompts import SYSTEM_PROMPT
from gmail_inbox_agent.models import EmailClassification, EmailMessage


CATEGORY_LABELS = {
    "work": "AI Work",
    "family": "AI Family",
    "money": "AI Money",
    "appointment": "AI Appointments",
    "receipt": "AI Receipts",
    "newsletter": "AI Newsletters",
    "spam_or_promo": "AI Low Priority",
}


class EmailClassifier:
    def __init__(self, api_key: str, model: str = "gpt-4.1-mini") -> None:
        self.api_key = api_key
        self.model = model
        self.client = OpenAI(api_key=api_key) if api_key else None

    def classify(self, message: EmailMessage) -> EmailClassification:
        if not self.client:
            return heuristic_classify(message)

        prompt = _build_user_prompt(message)
        response = self.client.responses.create(
            model=self.model,
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
        return EmailClassification.model_validate_json(response.output_text)


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
    labels = ["AI Reviewed"]
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
        labels.append("AI Important")
    if should_highlight:
        labels.append("AI Needs Attention")
    if importance == "low":
        labels.append("AI Low Priority")

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


def _build_user_prompt(message: EmailMessage) -> str:
    payload = {
        "subject": message.subject,
        "from_email": message.from_email,
        "to_email": message.to_email,
        "date": message.date,
        "snippet": message.snippet,
        "body_text": message.body_text,
        "existing_labels": message.existing_labels,
    }
    return json.dumps(payload, ensure_ascii=True)
