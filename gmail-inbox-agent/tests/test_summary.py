from datetime import UTC, datetime

from gmail_inbox_agent.models import AgentState, EmailClassification, EmailMessage, ProcessedEmail
from gmail_inbox_agent.reports.summary import build_summary, is_summary_email_subject, summary_subject


def test_summary_report_includes_highlighted_emails() -> None:
    state = AgentState(
        dry_run=True,
        processed=[
            ProcessedEmail(
                message=EmailMessage(
                    gmail_message_id="m1",
                    thread_id="t1",
                    subject="Doctor appointment",
                    from_email="clinic@example.com",
                    snippet="Please confirm",
                ),
                classification=EmailClassification(
                    importance="important",
                    category="appointment",
                    should_archive=False,
                    should_highlight=True,
                    labels_to_apply=["ai-reviewed", "ai-appointments", "ai-needs-attention"],
                    summary="Review and confirm",
                    reason="Appointment confirmation",
                    confidence=0.95,
                ),
            )
        ],
    )

    summary = build_summary(state)

    assert "Doctor appointment" in summary
    assert "## Needs Attention" in summary
    assert "Run At:" in summary


def test_summary_report_includes_actions() -> None:
    processed = ProcessedEmail(
        message=EmailMessage(
            gmail_message_id="m1",
            thread_id="t1",
            subject="Weekly newsletter",
            from_email="news@example.com",
            snippet="This week",
        ),
        classification=EmailClassification(
            importance="low",
            category="newsletter",
            should_archive=True,
            should_highlight=False,
            labels_to_apply=["ai-reviewed", "ai-newsletters"],
            summary="Newsletter",
            reason="Low-value newsletter",
            confidence=0.95,
        ),
        actions_taken=["apply labels: ai-newsletters, ai-reviewed", "archive: remove INBOX label"],
    )
    summary = build_summary(AgentState(dry_run=True, processed=[processed]))

    assert "## Actions" in summary
    assert "Weekly newsletter" in summary
    assert "Planned actions:" in summary


def test_summary_subject_includes_timestamp() -> None:
    subject = summary_subject(datetime(2026, 6, 26, 9, 30, 15, tzinfo=UTC))

    assert subject == "Gmail Agent Summary - 2026-06-26 09:30:15 UTC"


def test_summary_email_subject_detection() -> None:
    assert is_summary_email_subject("Gmail Agent Summary - 2026-06-26 09:30:15 PDT") is True
    assert is_summary_email_subject("Re: Gmail Agent Summary - 2026-06-26") is False
