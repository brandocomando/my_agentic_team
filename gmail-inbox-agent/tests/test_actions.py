from gmail_inbox_agent.gmail.actions import apply_actions, should_archive
from gmail_inbox_agent.models import EmailClassification, EmailMessage, ProcessedEmail


class FakeGmailClient:
    def __init__(self) -> None:
        self.calls = []

    def modify_message(self, message_id, add_label_names, remove_label_ids) -> None:
        self.calls.append(
            {
                "message_id": message_id,
                "add_label_names": add_label_names,
                "remove_label_ids": remove_label_ids,
            }
        )


def make_processed(confidence: float = 1.0, should_archive_value: bool = True) -> ProcessedEmail:
    return ProcessedEmail(
        message=EmailMessage(
            gmail_message_id="m1",
            thread_id="t1",
            subject="Promo",
            from_email="store@example.com",
            snippet="Sale",
        ),
        classification=EmailClassification(
            importance="low",
            category="newsletter",
            should_archive=should_archive_value,
            should_highlight=False,
            labels_to_apply=["AI Reviewed", "AI Newsletters"],
            summary="Sale",
            reason="promo",
            confidence=confidence,
        ),
    )


def test_archive_action_only_removes_inbox_label() -> None:
    client = FakeGmailClient()
    apply_actions(client, make_processed())

    assert client.calls[0]["remove_label_ids"] == ["INBOX"]


def test_archive_requires_confidence() -> None:
    assert should_archive(make_processed(confidence=0.69)) is False
