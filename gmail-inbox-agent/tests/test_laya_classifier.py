from unittest.mock import MagicMock

from gmail_inbox_agent.llm.classifier import EmailClassifier
from gmail_inbox_agent.llm.laya_classifier import (
    EMAIL_TRIAGE_QUESTIONS,
    LayaEmailClassifier,
    normalize_labels_in_classification,
)
from gmail_inbox_agent.models import EmailClassification, EmailMessage


def test_laya_schema_structure() -> None:
    assert "category" in EMAIL_TRIAGE_QUESTIONS
    assert EMAIL_TRIAGE_QUESTIONS["category"]["type"] == "choice"
    assert "work" in EMAIL_TRIAGE_QUESTIONS["category"]["criteria"]

    assert "importance" in EMAIL_TRIAGE_QUESTIONS
    assert EMAIL_TRIAGE_QUESTIONS["importance"]["type"] == "choice"

    assert "should_archive" in EMAIL_TRIAGE_QUESTIONS
    assert EMAIL_TRIAGE_QUESTIONS["should_archive"]["type"] == "noul"

    assert "should_highlight" in EMAIL_TRIAGE_QUESTIONS
    assert EMAIL_TRIAGE_QUESTIONS["should_highlight"]["type"] == "noul"


def test_laya_classifier_prediction_parsing() -> None:
    classifier = LayaEmailClassifier()
    message = EmailMessage(
        gmail_message_id="msg-101",
        thread_id="th-101",
        subject="Important contract review required",
        from_email="legal@enterprise.com",
        snippet="Please review the signed contract by end of day.",
    )

    mock_prediction = {
        "answers": {
            "category": {"choice": "work", "confidence": 0.96},
            "importance": {"choice": "important", "confidence": 0.94},
            "should_archive": {"noul": 0.05},
            "should_highlight": {"noul": 0.92},
        },
        "routing": {"model": "laya-modernbert"},
    }

    result = classifier.parse_prediction(mock_prediction, message)

    assert isinstance(result, EmailClassification)
    assert result.category == "work"
    assert result.importance == "important"
    assert result.should_archive is False
    assert result.should_highlight is True
    assert result.confidence == 0.94
    assert "ai-reviewed" in result.labels_to_apply
    assert "ai-work" in result.labels_to_apply
    assert "ai-important" in result.labels_to_apply
    assert "ai-needs-attention" in result.labels_to_apply
    assert "Laya System 1 decision" in result.reason


def test_laya_classifier_heuristic_fallback_when_router_none() -> None:
    classifier = LayaEmailClassifier(router_instance=None)
    # Ensure router is None
    classifier._ensure_router = lambda: None

    message = EmailMessage(
        gmail_message_id="msg-102",
        thread_id="th-102",
        subject="50% off summer sale",
        from_email="deals@store.com",
        snippet="Check out our discounted products today!",
    )

    result = classifier.classify(message)
    assert result.category == "spam_or_promo"
    assert result.importance == "low"
    assert result.should_archive is True
    assert "ai-low-priority" in result.labels_to_apply


def test_email_classifier_hybrid_mode_confident() -> None:
    classifier = EmailClassifier(provider="hybrid", laya_confidence_threshold=0.80)
    mock_laya = MagicMock()
    mock_laya.classify.return_value = EmailClassification(
        importance="important",
        category="work",
        should_archive=False,
        should_highlight=True,
        labels_to_apply=["ai-reviewed", "ai-work", "ai-important"],
        summary="Work offer",
        reason="Laya System 1 decision",
        confidence=0.92,
    )
    classifier.laya_classifier = mock_laya

    message = EmailMessage(
        gmail_message_id="msg-103",
        thread_id="th-103",
        subject="Job interview invitation",
        from_email="recruiter@tech.com",
        snippet="We would love to speak with you.",
    )

    result = classifier.classify(message)
    assert result.category == "work"
    assert result.confidence == 0.92
    mock_laya.classify.assert_called_once_with(message)


def test_email_classifier_hybrid_mode_low_confidence_fallback() -> None:
    classifier = EmailClassifier(provider="hybrid", laya_confidence_threshold=0.85, api_key="")
    mock_laya = MagicMock()
    # Confidence below threshold
    mock_laya.classify.return_value = EmailClassification(
        importance="normal",
        category="other",
        should_archive=False,
        should_highlight=False,
        labels_to_apply=["ai-reviewed"],
        summary="Ambiguous email",
        reason="Laya low confidence",
        confidence=0.55,
    )
    classifier.laya_classifier = mock_laya

    message = EmailMessage(
        gmail_message_id="msg-104",
        thread_id="th-104",
        subject="Order receipt #12345",
        from_email="billing@vendor.com",
        snippet="Your receipt for recent transaction.",
    )

    # In hybrid mode without OpenAI client, it falls back to heuristic/ollama
    result = classifier.classify(message)
    assert result.confidence is not None
