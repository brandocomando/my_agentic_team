from gmail_inbox_agent.models import AgentState, EmailClassification, EmailMessage, ProcessedEmail
from gmail_inbox_agent.reports.summary import build_summary


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
                    labels_to_apply=["AI Reviewed", "AI Appointments", "AI Needs Attention"],
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
