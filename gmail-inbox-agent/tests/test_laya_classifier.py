from unittest.mock import MagicMock

from gmail_inbox_agent.llm.classifier import EmailClassifier
from gmail_inbox_agent.llm.laya_classifier import (
    EMAIL_TRIAGE_QUESTIONS,
    LayaEmailClassifier,
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
    assert result.confidence == 0.92
    assert "ai-reviewed" in result.labels_to_apply
    assert "ai-work" in result.labels_to_apply
    assert "ai-important" in result.labels_to_apply
    assert "ai-needs-attention" in result.labels_to_apply
    assert "Laya System 1 decision" in result.reason


def test_laya_classifier_conflict_highlight_overrides_archive() -> None:
    classifier = LayaEmailClassifier()
    message = EmailMessage(
        gmail_message_id="msg-conflict",
        thread_id="th-conflict",
        subject="Urgent invoice review required",
        from_email="finance@vendor.com",
        snippet="Action required immediately.",
    )

    # Both archive and highlight probabilities are high
    mock_prediction = {
        "answers": {
            "category": {"choice": "money", "confidence": 0.95},
            "importance": {"choice": "important", "confidence": 0.92},
            "should_archive": {"noul": 0.95},
            "should_highlight": {"noul": 0.90},
        },
        "routing": {"model": "laya-modernbert"},
    }

    result = classifier.parse_prediction(mock_prediction, message)
    # Highlight / important MUST override archive
    assert result.should_highlight is True
    assert result.should_archive is False
    assert "ai-important" in result.labels_to_apply
    assert "ai-needs-attention" in result.labels_to_apply


def test_laya_classifier_router_initialization_error_handling() -> None:
    classifier = LayaEmailClassifier()
    # Simulate network or device failure when importing / constructing Router
    def failing_router():
        raise RuntimeError("CUDA out of memory or network failure")

    classifier._ensure_router = failing_router  # type: ignore[assignment]

    message = EmailMessage(
        gmail_message_id="msg-err",
        thread_id="th-err",
        subject="Invoice #999",
        from_email="billing@vendor.com",
        snippet="Invoice attached.",
    )

    # Must invoke classify() to verify that initialization failures are caught
    result = classifier.classify(message)
    assert result.category == "money"
    assert result.importance == "important"
    assert result.should_highlight is True
    assert result.should_archive is False
    assert result.confidence == 0.55


def test_laya_classifier_router_constructor_exception(monkeypatch) -> None:
    import sys

    mock_router_class = MagicMock(side_effect=RuntimeError("Download failed: 504 Gateway Timeout"))
    fake_laya = MagicMock()
    fake_laya.Router = mock_router_class
    monkeypatch.setitem(sys.modules, "laya", fake_laya)

    classifier = LayaEmailClassifier()
    message = EmailMessage(
        gmail_message_id="msg-err2",
        thread_id="th-err2",
        subject="Invoice #1000",
        from_email="billing@vendor.com",
        snippet="Invoice attached.",
    )

    result = classifier.classify(message)
    assert result.category == "money"
    assert result.confidence == 0.55
    assert classifier._router is None
    assert classifier._initialized is True


def test_laya_classifier_model_and_subfolder_configuration(monkeypatch) -> None:
    mock_router_class = MagicMock()
    mock_router_instance = MagicMock()
    mock_router_class.return_value = mock_router_instance

    import sys
    fake_laya = MagicMock()
    fake_laya.Router = mock_router_class
    monkeypatch.setitem(sys.modules, "laya", fake_laya)

    # 1. Standalone checkpoint repo: subfolder should not be redundantly appended
    classifier_standalone = LayaEmailClassifier(
        model_name="convaiinnovations/laya-multilingual",
        subfolder="multilingual",
    )
    router_standalone = classifier_standalone._ensure_router()
    assert router_standalone is mock_router_instance
    mock_router_class.assert_called_with(
        models={"multilingual": "convaiinnovations/laya-multilingual"},
        preload=True,
    )

    # 2. Bundled checkpoint repo: subfolder is correctly passed
    mock_router_class.reset_mock()
    classifier_bundle = LayaEmailClassifier(
        model_name="convaiinnovations/laya",
        subfolder="multilingual",
    )
    router_bundle = classifier_bundle._ensure_router()
    assert router_bundle is mock_router_instance
    mock_router_class.assert_called_with(
        models={"multilingual": ("convaiinnovations/laya", "multilingual")},
        preload=True,
    )

    # 3. Bundled checkpoint repo with subfolder="english": English weights reside at repo root
    mock_router_class.reset_mock()
    classifier_english = LayaEmailClassifier(
        model_name="convaiinnovations/laya",
        subfolder="english",
    )
    router_english = classifier_english._ensure_router()
    assert router_english is mock_router_instance
    mock_router_class.assert_called_with(
        models={"english": "convaiinnovations/laya"},
        preload=True,
    )


def test_laya_classifier_heuristic_invoice_categorized_as_money() -> None:
    classifier = LayaEmailClassifier(router_instance=None)
    classifier._ensure_router = lambda: None

    message = EmailMessage(
        gmail_message_id="msg-inv",
        thread_id="th-inv",
        subject="Invoice for recent services",
        from_email="billing@service.com",
        snippet="Please pay the outstanding balance.",
    )

    result = classifier.classify(message)
    assert result.category == "money"
    assert result.importance == "important"
    assert result.should_highlight is True
    assert result.should_archive is False
    assert result.confidence == 0.55
    assert "ai-money" in result.labels_to_apply
    assert "ai-important" in result.labels_to_apply


def test_laya_classifier_heuristic_fallback_when_router_none() -> None:
    classifier = LayaEmailClassifier(router_instance=None)
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
    assert result.confidence == 0.55
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


def test_email_classifier_hybrid_mode_low_confidence_fallback_openai() -> None:
    classifier = EmailClassifier(provider="hybrid", laya_confidence_threshold=0.85, api_key="test-key")
    mock_laya = MagicMock()
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

    openai_classification = EmailClassification(
        importance="important",
        category="work",
        should_archive=False,
        should_highlight=True,
        labels_to_apply=["ai-reviewed", "ai-work"],
        summary="OpenAI deep classification",
        reason="OpenAI System 2 reasoning",
        confidence=0.95,
    )
    classifier._classify_with_openai = MagicMock(return_value=openai_classification)

    message = EmailMessage(
        gmail_message_id="msg-104",
        thread_id="th-104",
        subject="Contract proposal",
        from_email="client@vendor.com",
        snippet="Proposal details enclosed.",
    )

    result = classifier.classify(message)
    assert result == openai_classification
    classifier._classify_with_openai.assert_called_once_with(message)


def test_email_classifier_hybrid_mode_low_confidence_fallback_ollama() -> None:
    classifier = EmailClassifier(
        provider="hybrid",
        laya_confidence_threshold=0.85,
        api_key="",
        ollama_base_url="http://localhost:11434",
    )
    mock_laya = MagicMock()
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

    ollama_classification = EmailClassification(
        importance="low",
        category="newsletter",
        should_archive=True,
        should_highlight=False,
        labels_to_apply=["ai-reviewed", "ai-newsletters"],
        summary="Ollama deep classification",
        reason="Ollama System 2 reasoning",
        confidence=0.90,
    )
    classifier._classify_with_ollama = MagicMock(return_value=ollama_classification)

    message = EmailMessage(
        gmail_message_id="msg-105",
        thread_id="th-105",
        subject="Weekly digest",
        from_email="news@daily.com",
        snippet="Here is your digest.",
    )

    result = classifier.classify(message)
    assert result == ollama_classification
    classifier._classify_with_ollama.assert_called_once_with(message)
