from __future__ import annotations

from collections import Counter
from datetime import datetime

from gmail_inbox_agent.gmail.actions import labels_for, should_archive
from gmail_inbox_agent.models import AgentState, ProcessedEmail

SUMMARY_SUBJECT_PREFIX = "Gmail Inbox Agent Summary"
# Keep old summaries out of the inbox scan after the project naming cleanup.
LEGACY_SUMMARY_SUBJECT_PREFIXES = ("Gmail Agent Summary",)


def summary_subject(run_at: datetime | None = None) -> str:
    timestamp = _run_timestamp(run_at)
    return f"{SUMMARY_SUBJECT_PREFIX} - {timestamp}"


def build_summary(state: AgentState) -> str:
    run_at = datetime.now().astimezone()
    processed = state.processed
    archived = [item for item in processed if should_archive(item)]
    highlighted = [item for item in processed if item.classification.should_highlight]
    label_counts = Counter(label for item in processed for label in labels_for(item))

    lines = [
        "# Gmail Inbox Agent Summary",
        "",
        f"Processed: {len(processed)}",
        f"Archived: {len(archived)}",
        f"Highlighted: {len(highlighted)}",
        f"Dry Run: {str(state.dry_run).lower()}",
        f"Run At: {_run_timestamp(run_at)}",
        "",
        "## Needs Attention",
        "",
    ]

    if highlighted:
        for item in highlighted:
            lines.extend(_highlight_lines(item))
    else:
        lines.append("None")
        lines.append("")

    lines.extend(["## Archived / Low Priority", ""])
    if archived:
        lines.extend(f"- {item.message.subject or item.message.snippet}" for item in archived)
    else:
        lines.append("None")

    lines.extend(["", "## Labels Applied", ""])
    if label_counts:
        lines.extend(f"- {label}: {count}" for label, count in sorted(label_counts.items()))
    else:
        lines.append("None")

    lines.extend(["", "## Actions", ""])
    if processed:
        for item in processed:
            lines.extend(_action_lines(item, state.dry_run))
    else:
        lines.append("None")

    lines.extend(["", "## Errors", ""])
    if state.errors:
        lines.extend(f"- {error}" for error in state.errors)
    else:
        lines.append("None")

    return "\n".join(lines)


def is_summary_email_subject(subject: str) -> bool:
    normalized = subject.strip().lower()
    prefixes = (SUMMARY_SUBJECT_PREFIX, *LEGACY_SUMMARY_SUBJECT_PREFIXES)
    return any(normalized.startswith(prefix.lower()) for prefix in prefixes)


def _highlight_lines(item: ProcessedEmail) -> list[str]:
    message = item.message
    classification = item.classification
    return [
        f"### {message.subject or '(no subject)'}",
        f"From: {message.from_email}",
        f"Category: {classification.category}",
        f"Reason: {classification.reason}",
        f"Suggested action: {classification.summary}",
        "",
    ]


def _action_lines(item: ProcessedEmail, dry_run: bool) -> list[str]:
    message = item.message
    classification = item.classification
    mode = "Planned" if dry_run else "Applied"
    archive = "yes" if should_archive(item) else "no"
    actions = ", ".join(item.actions_taken) if item.actions_taken else "No action recorded"
    return [
        f"### {message.subject or '(no subject)'}",
        f"From: {message.from_email}",
        f"Category: {classification.category}",
        f"Importance: {classification.importance}",
        f"Archive: {archive}",
        f"{mode} actions: {actions}",
        "",
    ]


def _run_timestamp(run_at: datetime | None = None) -> str:
    value = run_at or datetime.now().astimezone()
    if value.tzinfo is None:
        value = value.astimezone()
    timestamp = value.strftime("%Y-%m-%d %H:%M:%S")
    timezone = value.tzname()
    if timezone:
        return f"{timestamp} {timezone}"
    return timestamp
