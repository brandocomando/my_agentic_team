from gmail_inbox_agent.llm import classifier as classifier_module
from gmail_inbox_agent.llm.classifier import EmailClassifier, _build_user_prompt, heuristic_classify, normalize_classification
from gmail_inbox_agent.models import EmailClassification, EmailMessage


def test_classifier_output_validates_against_model() -> None:
    message = EmailMessage(
        gmail_message_id="m1",
        thread_id="t1",
        subject="Interview request",
        from_email="recruiter@example.com",
        snippet="Can you meet tomorrow?",
    )

    classification = heuristic_classify(message)

    assert isinstance(classification, EmailClassification)
    assert classification.category == "work"
    assert classification.should_highlight is True
    assert "ai-reviewed" in classification.labels_to_apply


def test_classifier_normalizes_legacy_label_names() -> None:
    classification = normalize_classification(
        EmailClassification(
            importance="important",
            category="work",
            should_archive=False,
            should_highlight=True,
            labels_to_apply=["AI Reviewed", "AI Work", "AI Needs Attention"],
            summary="Interview",
            reason="Job opportunity",
            confidence=0.9,
        )
    )

    assert classification.labels_to_apply == ["ai-needs-attention", "ai-reviewed", "ai-work"]


def test_prompt_includes_personal_rules() -> None:
    message = EmailMessage(
        gmail_message_id="m1",
        thread_id="t1",
        subject="Hello",
        from_email="person@example.com",
        snippet="Hi",
    )

    prompt = _build_user_prompt(message, "Apply ai-work to example.com.")

    assert "personal_classification_rules" in prompt
    assert "Apply ai-work to example.com." in prompt


def test_openai_provider_without_key_uses_heuristic_fallback() -> None:
    message = EmailMessage(
        gmail_message_id="m1",
        thread_id="t1",
        subject="Receipt for your order",
        from_email="store@example.com",
        snippet="Order confirmation",
    )

    classification = EmailClassifier(provider="openai", api_key="").classify(message)

    assert classification.category == "receipt"
    assert classification.should_archive is True


def test_ollama_provider_parses_structured_output(monkeypatch) -> None:
    captured = {}

    def fake_post_ollama_generate(base_url: str, payload: dict) -> dict:
        captured["base_url"] = base_url
        captured["payload"] = payload
        return {
            "response": EmailClassification(
                importance="normal",
                category="work",
                should_archive=False,
                should_highlight=False,
                labels_to_apply=["AI Work"],
                summary="Work update",
                reason="Project domain",
                confidence=0.8,
            ).model_dump_json()
        }

    monkeypatch.setattr(classifier_module, "_post_ollama_generate", fake_post_ollama_generate)
    message = EmailMessage(
        gmail_message_id="m1",
        thread_id="t1",
        subject="Project update",
        from_email="person@example.com",
        snippet="Status update",
    )

    classification = EmailClassifier(
        provider="ollama",
        ollama_model="llama3.1:8b",
        ollama_base_url="http://localhost:11434/",
    ).classify(message)

    assert captured["base_url"] == "http://localhost:11434"
    assert captured["payload"]["model"] == "llama3.1:8b"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["format"]["title"] == "EmailClassification"
    assert classification.labels_to_apply == ["ai-reviewed", "ai-work"]
