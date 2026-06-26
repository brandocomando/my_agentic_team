from gmail_inbox_agent.llm.classifier import heuristic_classify
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
    assert "AI Reviewed" in classification.labels_to_apply
