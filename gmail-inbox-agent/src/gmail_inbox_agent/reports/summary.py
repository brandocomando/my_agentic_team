from __future__ import annotations

from collections import Counter
from datetime import date

from gmail_inbox_agent.gmail.actions import labels_for, should_archive
from gmail_inbox_agent.models import AgentState, ProcessedEmail


def summary_subject(today: date | None = None) -> str:
    return f"Gmail Agent Summary - {(today or date.today()).isoformat()}"


def build_summary(state: AgentState) -> str:
    processed = state.processed
    archived = [item for item in processed if should_archive(item)]
    highlighted = [item for item in processed if item.classification.should_highlight]
    label_counts = Counter(label for item in processed for label in labels_for(item))

    lines = [
        "# Gmail Agent Summary",
        "",
        f"Processed: {len(processed)}",
        f"Archived: {len(archived)}",
        f"Highlighted: {len(highlighted)}",
        f"Dry Run: {str(state.dry_run).lower()}",
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

    lines.extend(["", "## Errors", ""])
    if state.errors:
        lines.extend(f"- {error}" for error in state.errors)
    else:
        lines.append("None")

    return "\n".join(lines)


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
