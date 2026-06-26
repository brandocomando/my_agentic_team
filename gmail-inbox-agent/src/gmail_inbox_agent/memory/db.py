from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
create table if not exists reviewed_messages (
  gmail_message_id text primary key,
  thread_id text,
  subject text,
  from_email text,
  reviewed_at text,
  decision text,
  applied_labels text,
  archived boolean
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn
