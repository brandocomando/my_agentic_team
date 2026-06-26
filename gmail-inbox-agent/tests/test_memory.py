from gmail_inbox_agent.memory.reviewed_messages import ReviewedMessageStore
from gmail_inbox_agent.models import EmailClassification, EmailMessage, ProcessedEmail


def test_sqlite_memory_records_reviewed_messages(tmp_path) -> None:
    store = ReviewedMessageStore(tmp_path / "memory.sqlite")
    processed = ProcessedEmail(
        message=EmailMessage(
            gmail_message_id="m1",
            thread_id="t1",
            subject="Hello",
            from_email="a@example.com",
            snippet="Hi",
        ),
        classification=EmailClassification(
            importance="normal",
            category="other",
            should_archive=False,
            should_highlight=False,
            labels_to_apply=["AI Reviewed"],
            summary="Hi",
            reason="test",
            confidence=1,
        ),
    )

    assert store.is_reviewed("m1") is False
    store.record(processed)
    assert store.is_reviewed("m1") is True
