from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from gmail_inbox_agent.memory.db import connect
from gmail_inbox_agent.models import ProcessedEmail


class ReviewedMessageStore:
    def __init__(self, db_path: Path) -> None:
        self.conn = connect(db_path)

    def is_reviewed(self, gmail_message_id: str) -> bool:
        row = self.conn.execute(
            "select 1 from reviewed_messages where gmail_message_id = ?",
            (gmail_message_id,),
        ).fetchone()
        return row is not None

    def record(self, processed: ProcessedEmail) -> None:
        message = processed.message
        classification = processed.classification
        self.conn.execute(
            """
            insert or replace into reviewed_messages (
              gmail_message_id, thread_id, subject, from_email, reviewed_at,
              decision, applied_labels, archived
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.gmail_message_id,
                message.thread_id,
                message.subject,
                message.from_email,
                datetime.now(UTC).isoformat(),
                classification.category,
                json.dumps(classification.labels_to_apply),
                classification.should_archive,
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def make_memory(path: Path) -> ReviewedMessageStore:
    return ReviewedMessageStore(path)
