from __future__ import annotations

import logging
from typing import Any

from gmail_inbox_agent.labels import (
    CATEGORY_LABELS,
    IMPORTANT_LABEL,
    LOW_PRIORITY_LABEL,
    NEEDS_ATTENTION_LABEL,
    REVIEWED_LABEL,
    normalize_labels,
)
from gmail_inbox_agent.models import EmailClassification, EmailMessage

logger = logging.getLogger(__name__)

# Standard Laya question schema for email triage
EMAIL_TRIAGE_QUESTIONS: dict[str, Any] = {
    "category": {
        "type": "choice",
        "instructions": "What is the primary category of this email?",
        "criteria": {
            "work": "job offers, interviews, work projects, professional communications, business inquiries",
            "family": "family, personal friends, personal relationships",
            "money": "banking, investments, credit cards, bills, tax documents, financial statements",
            "appointment": "doctor appointments, calendar events, meeting invites, dentist, reservations",
            "receipt": "order confirmations, purchase receipts, shipping notifications, delivery updates",
            "newsletter": "editorial digests, news summaries, tech updates, industry blogs",
            "account": "security codes, password resets, 2FA codes, account verification",
            "spam_or_promo": "promotional discounts, marketing campaigns, sales cold outreach, spam",
            "other": "everything else that does not fit into any other category",
        },
    },
    "importance": {
        "type": "choice",
        "instructions": "How important is this email?",
        "criteria": {
            "important": "time-sensitive, critical actions, urgent inquiries, direct communication from real humans",
            "normal": "standard informational emails, expected updates, ordinary business or personal mail",
            "low": "promotions, automated marketing, newsletters, low-priority receipts, bulk announcements",
        },
    },
    "should_archive": {
        "type": "noul",
        "instructions": "Should this email be safely archived away from the main inbox (e.g. promotional, newsletter, or automated notification)?",
    },
    "should_highlight": {
        "type": "noul",
        "instructions": "Does this email require urgent attention or immediate user action?",
    },
}


class LayaEmailClassifier:
    """System 1 decision engine for sub-50ms email classification using Laya."""

    def __init__(
        self,
        model_name: str = "convaiinnovations/laya",
        subfolder: str | None = None,
        confidence_threshold: float = 0.85,
        router_instance: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self.subfolder = subfolder
        self.confidence_threshold = confidence_threshold
        self._router = router_instance
        self._initialized = router_instance is not None

    def _ensure_router(self) -> Any:
        if self._router is None:
            try:
                from laya import Router

                self._router = Router(preload=True)
                self._initialized = True
            except ImportError:
                logger.warning("laya package not installed; falling back to heuristic decision runner.")
                self._router = None
                self._initialized = False
        return self._router

    def build_state(self, message: EmailMessage) -> dict[str, Any]:
        return {
            "subject": message.subject,
            "from_email": message.from_email,
            "snippet": message.snippet,
            "body": (message.body_text or message.snippet)[:1024],
        }

    def classify(self, message: EmailMessage) -> EmailClassification:
        router = self._ensure_router()
        state = self.build_state(message)

        if router is not None:
            try:
                prediction = router.predict(state, EMAIL_TRIAGE_QUESTIONS)
                return self.parse_prediction(prediction, message)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Laya prediction failed: %s; falling back to heuristic.", exc)

        return self._heuristic_laya_fallback(message)

    def parse_prediction(self, prediction: dict[str, Any], message: EmailMessage) -> EmailClassification:
        answers = prediction.get("answers", {})

        cat_data = answers.get("category", {})
        category = cat_data.get("choice", "other")
        category_conf = float(cat_data.get("confidence", 0.85))

        imp_data = answers.get("importance", {})
        importance = imp_data.get("choice", "normal")
        imp_conf = float(imp_data.get("confidence", 0.85))

        archive_prob = float(answers.get("should_archive", {}).get("noul", 0.0))
        highlight_prob = float(answers.get("should_highlight", {}).get("noul", 0.0))

        should_archive = archive_prob >= 0.50
        should_highlight = highlight_prob >= 0.50

        # Calibrated aggregate confidence
        confidence = round(min(category_conf, imp_conf), 4)

        labels: list[str] = [REVIEWED_LABEL]
        if category in CATEGORY_LABELS:
            labels.append(CATEGORY_LABELS[category])
        if importance == "important" or should_highlight:
            labels.append(IMPORTANT_LABEL)
            labels.append(NEEDS_ATTENTION_LABEL)
        elif importance == "low" or should_archive:
            labels.append(LOW_PRIORITY_LABEL)

        routing_model = prediction.get("routing", {}).get("model", "laya-modernbert")

        return normalize_labels_in_classification(
            EmailClassification(
                importance=importance if importance in {"important", "normal", "low"} else "normal",
                category=category if category in CATEGORY_LABELS else "other",
                should_archive=should_archive,
                should_highlight=should_highlight,
                labels_to_apply=labels,
                summary=f"{importance.title()} {category} email: {message.subject[:60]}",
                reason=f"Laya System 1 decision via {routing_model} (confidence={confidence:.2f})",
                confidence=confidence,
            )
        )

    def _heuristic_laya_fallback(self, message: EmailMessage) -> EmailClassification:
        text = f"{message.subject} {message.from_email} {message.snippet}".lower()
        category = "other"
        importance = "normal"
        should_archive = False
        should_highlight = False

        if any(w in text for w in ["interview", "offer", "meeting", "resume", "client", "project"]):
            category = "work"
            importance = "important"
            should_highlight = True
        elif any(w in text for w in ["receipt", "order confirmation", "shipped", "invoice"]):
            category = "receipt"
            importance = "low"
            should_archive = True
        elif any(w in text for w in ["sale", "discount", "unsubscribe", "% off", "deal"]):
            category = "spam_or_promo"
            importance = "low"
            should_archive = True
        elif any(w in text for w in ["newsletter", "digest", "weekly"]):
            category = "newsletter"
            importance = "low"
            should_archive = True
        elif any(w in text for w in ["bank", "statement", "credit card", "tax", "wire"]):
            category = "money"
            importance = "important"

        labels = [REVIEWED_LABEL]
        if category in CATEGORY_LABELS:
            labels.append(CATEGORY_LABELS[category])
        if importance == "important":
            labels.extend([IMPORTANT_LABEL, NEEDS_ATTENTION_LABEL])
        elif importance == "low":
            labels.append(LOW_PRIORITY_LABEL)

        return normalize_labels_in_classification(
            EmailClassification(
                importance=importance,
                category=category,
                should_archive=should_archive,
                should_highlight=should_highlight,
                labels_to_apply=labels,
                summary=f"{importance.title()} {category}: {message.subject[:60]}",
                reason="Laya System 1 fallback (heuristic emulator)",
                confidence=0.88,
            )
        )


def normalize_labels_in_classification(classification: EmailClassification) -> EmailClassification:
    classification.labels_to_apply = normalize_labels(classification.labels_to_apply)
    return classification
