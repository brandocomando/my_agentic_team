from __future__ import annotations

import sqlite3
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover - psycopg is an optional runtime dependency path.
    psycopg = None


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


def connect_sqlite(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def connect_postgres(database_url: str):
    if psycopg is None:
        raise RuntimeError("Postgres memory backend requires psycopg to be installed.")
    if not database_url:
        raise ValueError("DATABASE_URL is required when MEMORY_BACKEND=postgres.")
    conn = psycopg.connect(database_url)
    conn.execute(SCHEMA)
    conn.commit()
    return conn
