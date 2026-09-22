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
        self._target_model: str | None = None

    def _ensure_router(self) -> Any:
        if self._router is None and not self._initialized:
            try:
                from laya import Router

                models_override = None
                if self.subfolder is not None or self.model_name != "convaiinnovations/laya":
                    slot = "english"
                    if self.subfolder in ("multilingual", "typed-decisions", "english"):
                        slot = self.subfolder
                    elif any(k in self.model_name for k in ("multi", "typed")):
                        slot = "multilingual" if "multi" in self.model_name else "typed-decisions"

                    # If model_name is already a standalone checkpoint repo corresponding to the slot,
                    # its weights reside at the repo root (no subfolder).
                    sub = self.subfolder
                    if sub and (
                        self.model_name.rstrip("/").endswith(f"-{sub}")
                        or self.model_name.rstrip("/").endswith(f"/{sub}")
                        or (slot in self.model_name and self.model_name != "convaiinnovations/laya")
                    ):
                        sub = None

                    models_override = {slot: (self.model_name, sub) if sub else self.model_name}
                    self._target_model = slot

                self._router = Router(models=models_override, preload=True)
                self._initialized = True
            except ImportError:
                logger.warning("laya package not installed; falling back to heuristic decision runner.")
                self._router = None
                self._initialized = True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to initialize Laya Router: %s; falling back to heuristic decision runner.", exc
                )
                self._router = None
                self._initialized = True
        return self._router

    def build_state(self, message: EmailMessage) -> dict[str, Any]:
        return {
            "subject": message.subject,
            "from_email": message.from_email,
            "snippet": message.snippet,
            "body": (message.body_text or message.snippet)[:1024],
        }

    def classify(self, message: EmailMessage) -> EmailClassification:
        try:
            router = self._ensure_router()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to obtain Laya router: %s; falling back to heuristic.", exc)
            router = None

        state = self.build_state(message)

        if router is not None:
            try:
                kwargs: dict[str, Any] = {}
                if self._target_model is not None:
                    kwargs["model"] = self._target_model
                prediction = router.predict(state, EMAIL_TRIAGE_QUESTIONS, **kwargs)
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

        # Require high confidence for destructive archive action
        archive_cutoff = max(self.confidence_threshold, 0.70)
        should_archive = archive_prob >= archive_cutoff
        should_highlight = highlight_prob >= 0.50

        # Urgent / important emails must never be archived
        if should_highlight or importance == "important":
            should_archive = False

        # Calibrated aggregate confidence incorporates all active decisions
        archive_conf = archive_prob if should_archive else (1.0 - archive_prob)
        highlight_conf = highlight_prob if should_highlight else (1.0 - highlight_prob)
        confidence = round(min(category_conf, imp_conf, archive_conf, highlight_conf), 4)

        labels: list[str] = [REVIEWED_LABEL]
        if category in CATEGORY_LABELS:
            labels.append(CATEGORY_LABELS[category])
        if importance == "important":
            labels.append(IMPORTANT_LABEL)
        if should_highlight:
            labels.append(NEEDS_ATTENTION_LABEL)
        if importance == "low" or should_archive:
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

        if any(w in text for w in ["invoice", "bill", "bank", "tax", "payment", "refund", "wire"]):
            category = "money"
            importance = "important"
            should_highlight = True
        elif any(w in text for w in ["meeting", "appointment", "calendar", "schedule"]):
            category = "appointment"
            importance = "important"
            should_highlight = True
        elif any(w in text for w in ["interview", "offer", "resume", "client", "project", "job", "recruiter", "deadline"]):
            category = "work"
            importance = "important"
            should_highlight = True
        elif any(w in text for w in ["receipt", "order confirmation", "shipped"]):
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

        if should_highlight or importance == "important":
            should_archive = False

        labels = [REVIEWED_LABEL]
        if category in CATEGORY_LABELS:
            labels.append(CATEGORY_LABELS[category])
        if importance == "important":
            labels.append(IMPORTANT_LABEL)
        if should_highlight:
            labels.append(NEEDS_ATTENTION_LABEL)
        if importance == "low" or should_archive:
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
                confidence=0.55,
            )
        )


def normalize_labels_in_classification(classification: EmailClassification) -> EmailClassification:
    classification.labels_to_apply = normalize_labels(classification.labels_to_apply)
    return classification
