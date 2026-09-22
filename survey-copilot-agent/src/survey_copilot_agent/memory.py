import json
import math
import sqlite3
from pathlib import Path

from .models import Fact


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'profile',
                    embedding_json TEXT
                )
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(facts)").fetchall()
            }
            if "source" not in columns:
                conn.execute("ALTER TABLE facts ADD COLUMN source TEXT NOT NULL DEFAULT 'profile'")
            conn.execute("UPDATE facts SET source = 'learned' WHERE key LIKE 'learned\\_%' ESCAPE '\\'")

    def upsert_fact(self, fact: Fact, embedding: list[float] | None = None) -> None:
        embedding_json = json.dumps(embedding) if embedding is not None else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO facts (key, value, text, source, embedding_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    text = excluded.text,
                    source = excluded.source,
                    embedding_json = COALESCE(excluded.embedding_json, facts.embedding_json)
                """,
                (fact.key, fact.value, fact.text, fact.source, embedding_json),
            )

    def all_facts(self) -> list[Fact]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value, text, source FROM facts ORDER BY key").fetchall()
        return [Fact(key=row["key"], value=row["value"], text=row["text"], source=row["source"]) for row in rows]

    def learned_facts(self) -> list[Fact]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, value, text, source FROM facts
                WHERE source = 'learned' OR key LIKE 'learned\\_%' ESCAPE '\\'
                ORDER BY key
                """
            ).fetchall()
        return [Fact(key=row["key"], value=row["value"], text=row["text"], source=row["source"]) for row in rows]

    def delete_learned_fact(self, key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM facts
                WHERE key = ? AND (source = 'learned' OR key LIKE 'learned\\_%' ESCAPE '\\')
                """,
                (key,),
            )
        return cursor.rowcount > 0

    def search(self, query_embedding: list[float], limit: int = 4) -> list[tuple[Fact, float]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value, text, source, embedding_json FROM facts WHERE embedding_json IS NOT NULL"
            ).fetchall()

        scored: list[tuple[Fact, float]] = []
        for row in rows:
            embedding = json.loads(row["embedding_json"])
            score = cosine_similarity(query_embedding, embedding)
            scored.append((Fact(key=row["key"], value=row["value"], text=row["text"], source=row["source"]), score))

        return sorted(scored, key=lambda item: (item[1], source_priority(item[0].source)), reverse=True)[:limit]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def load_profile(path: Path) -> list[Fact]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    facts = data.get("facts", [])
    return [Fact.model_validate({**fact, "source": "profile"}) for fact in facts]


def source_priority(source: str) -> int:
    return 1 if source == "profile" else 0


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
