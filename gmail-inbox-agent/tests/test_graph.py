from pathlib import Path

from gmail_inbox_agent.graph import apply_gmail_actions, filter_unreviewed_messages
from gmail_inbox_agent.memory.reviewed_messages import ReviewedMessageStore
from gmail_inbox_agent.models import AgentState, EmailClassification, EmailMessage, ProcessedEmail


class MutatingClient:
    def __init__(self) -> None:
        self.called = False

    def modify_message(self, *args, **kwargs) -> None:
        self.called = True


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
                existing_labels=["AI Reviewed"],
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
            labels_to_apply=["AI Reviewed", "AI Newsletters"],
            summary="Sale",
            reason="promo",
            confidence=1,
        ),
    )
    state = AgentState(dry_run=True, gmail_client=client, processed=[processed])

    apply_gmail_actions(state)

    assert client.called is False
    assert processed.actions_taken
