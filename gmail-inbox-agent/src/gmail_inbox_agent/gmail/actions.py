from __future__ import annotations

from gmail_inbox_agent.labels import REVIEWED_LABEL, normalize_labels
from gmail_inbox_agent.models import ProcessedEmail


MIN_ARCHIVE_CONFIDENCE = 0.7


def planned_actions(processed: ProcessedEmail) -> list[str]:
    classification = processed.classification
    actions = [f"apply labels: {', '.join(labels_for(processed))}"]
    if should_archive(processed):
        actions.append("archive: remove INBOX label")
    return actions


def apply_actions(gmail_client: object, processed: ProcessedEmail) -> list[str]:
    labels = labels_for(processed)
    remove_labels = ["INBOX"] if should_archive(processed) else []
    gmail_client.modify_message(
        processed.message.gmail_message_id,
        add_label_names=labels,
        remove_label_ids=remove_labels,
    )
    return planned_actions(processed)


def labels_for(processed: ProcessedEmail) -> list[str]:
    return normalize_labels([REVIEWED_LABEL, *processed.classification.labels_to_apply])


def should_archive(processed: ProcessedEmail) -> bool:
    classification = processed.classification
    return classification.should_archive and classification.confidence >= MIN_ARCHIVE_CONFIDENCE
