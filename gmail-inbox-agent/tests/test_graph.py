from pathlib import Path

from gmail_inbox_agent.graph import apply_gmail_actions, filter_unreviewed_messages, send_summary
from gmail_inbox_agent.memory.reviewed_messages import ReviewedMessageStore
from gmail_inbox_agent.models import AgentState, EmailClassification, EmailMessage, ProcessedEmail


class MutatingClient:
    def __init__(self) -> None:
        self.called = False

    def modify_message(self, *args, **kwargs) -> None:
        self.called = True


class SummaryClient:
    def __init__(self) -> None:
        self.sent = False

    def send_email(self, *args, **kwargs) -> None:
        self.sent = True


def test_already_reviewed_messages_are_skipped(tmp_path: Path) -> None:
    memory = ReviewedMessageStore(tmp_path / "memory.sqlite")
    state = AgentState(
        memory=memory,
        messages=[
            EmailMessage(
                gmail_message_id="m1",
                thread_id="t1",
                subject="Done",
                from_email="a@example.com",
                snippet="Reviewed",
                existing_labels=["ai-reviewed"],
            )
        ],
    )

    result = filter_unreviewed_messages(state)

    assert result.unreviewed_messages == []


def test_legacy_reviewed_label_is_skipped(tmp_path: Path) -> None:
    memory = ReviewedMessageStore(tmp_path / "memory.sqlite")
    state = AgentState(
        memory=memory,
        messages=[
            EmailMessage(
                gmail_message_id="m1",
                thread_id="t1",
                subject="Done",
                from_email="a@example.com",
                snippet="Reviewed",
                existing_labels=["AI Reviewed"],
            )
        ],
    )

    result = filter_unreviewed_messages(state)

    assert result.unreviewed_messages == []


def test_agent_summary_emails_are_skipped(tmp_path: Path) -> None:
    memory = ReviewedMessageStore(tmp_path / "memory.sqlite")
    state = AgentState(
        memory=memory,
        messages=[
            EmailMessage(
                gmail_message_id="m1",
                thread_id="t1",
                subject="Gmail Agent Summary - 2026-06-26 09:30:15 PDT",
                from_email="me@example.com",
                snippet="Processed: 1",
            )
        ],
    )

    result = filter_unreviewed_messages(state)

    assert result.unreviewed_messages == []


def test_dry_run_does_not_call_gmail_mutations() -> None:
    client = MutatingClient()
    processed = ProcessedEmail(
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
            should_archive=True,
            should_highlight=False,
            labels_to_apply=["ai-reviewed", "ai-newsletters"],
            summary="Sale",
            reason="promo",
            confidence=1,
        ),
    )
    state = AgentState(dry_run=True, gmail_client=client, processed=[processed])

    apply_gmail_actions(state)

    assert client.called is False
    assert processed.actions_taken


def test_apply_run_does_not_send_summary_when_no_new_emails() -> None:
    client = SummaryClient()
    state = AgentState(dry_run=False, gmail_client=client, processed=[])

    send_summary(state)

    assert client.sent is False
