from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from gmail_inbox_agent.memory.db import connect_postgres, connect_sqlite
from gmail_inbox_agent.models import ProcessedEmail


class ReviewedMessageStore:
    def __init__(
        self,
        db_path: Path | None = None,
        backend: Literal["sqlite", "postgres"] = "sqlite",
        database_url: str = "",
    ) -> None:
        self.backend = backend
        self.placeholder = "?" if backend == "sqlite" else "%s"
        if backend == "postgres":
            self.conn = connect_postgres(database_url)
        else:
            if db_path is None:
                raise ValueError("db_path is required when MEMORY_BACKEND=sqlite.")
            self.conn = connect_sqlite(db_path)

    def is_reviewed(self, gmail_message_id: str) -> bool:
        row = self.conn.execute(
            f"select 1 from reviewed_messages where gmail_message_id = {self.placeholder}",
            (gmail_message_id,),
        ).fetchone()
        return row is not None

    def record(self, processed: ProcessedEmail) -> None:
        message = processed.message
        classification = processed.classification
        placeholders = ", ".join([self.placeholder] * 8)
        if self.backend == "postgres":
            sql = f"""
                insert into reviewed_messages (
                  gmail_message_id, thread_id, subject, from_email, reviewed_at,
                  decision, applied_labels, archived
                ) values ({placeholders})
                on conflict (gmail_message_id) do update set
                  thread_id = excluded.thread_id,
                  subject = excluded.subject,
                  from_email = excluded.from_email,
                  reviewed_at = excluded.reviewed_at,
                  decision = excluded.decision,
                  applied_labels = excluded.applied_labels,
                  archived = excluded.archived
                """
        else:
            sql = f"""
                insert or replace into reviewed_messages (
                  gmail_message_id, thread_id, subject, from_email, reviewed_at,
                  decision, applied_labels, archived
                ) values ({placeholders})
                """
        self.conn.execute(
            sql,
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


def make_memory_store(
    backend: Literal["sqlite", "postgres"],
    db_path: Path,
    database_url: str = "",
) -> ReviewedMessageStore:
    return ReviewedMessageStore(db_path=db_path, backend=backend, database_url=database_url)
