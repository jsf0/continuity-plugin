"""SQLite storage for continuity memory records."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from continuity.models import ContextRecord, SkillLink, SourceRef, utc_now
from continuity.security import sanitize_observation_text

SCHEMA_VERSION = 3


@dataclass(frozen=True)
class FtsHit:
    """A raw FTS search hit."""

    record: ContextRecord
    rank: float


class ContinuityStore:
    """SQLite-backed continuity memory store."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).expanduser()

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version INTEGER PRIMARY KEY,
                  applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS context_records (
                  id TEXT PRIMARY KEY,
                  kind TEXT NOT NULL,
                  scope_user TEXT,
                  scope_project TEXT,
                  scope_repo TEXT,
                  scope_profile TEXT,
                  title TEXT NOT NULL,
                  summary TEXT NOT NULL,
                  details TEXT,
                  tags_json TEXT NOT NULL DEFAULT '[]',
                  entities_json TEXT NOT NULL DEFAULT '[]',
                  sources_json TEXT NOT NULL DEFAULT '[]',
                  confidence REAL NOT NULL DEFAULT 0.5,
                  importance REAL NOT NULL DEFAULT 0.5,
                  trust_level TEXT NOT NULL DEFAULT 'session_extracted',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  last_accessed_at TEXT,
                  last_confirmed_at TEXT,
                  expires_at TEXT,
                  source_hash TEXT,
                  embedding_text TEXT
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS context_records_fts USING fts5(
                  id UNINDEXED,
                  title,
                  summary,
                  details,
                  tags,
                  entities,
                  tokenize = "unicode61 tokenchars '_-:'"
                );

                CREATE TABLE IF NOT EXISTS session_observations (
                  id TEXT PRIMARY KEY,
                  session_id TEXT NOT NULL,
                  turn_index INTEGER,
                  user_content TEXT,
                  assistant_content TEXT,
                  created_at TEXT NOT NULL,
                  consolidated INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS retrieval_events (
                  id TEXT PRIMARY KEY,
                  query TEXT NOT NULL,
                  selected_ids_json TEXT NOT NULL,
                  skipped_ids_json TEXT NOT NULL DEFAULT '[]',
                  scores_json TEXT NOT NULL DEFAULT '{}',
                  max_chars INTEGER,
                  created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS context_record_vectors (
                  record_id TEXT NOT NULL,
                  model TEXT NOT NULL,
                  dimensions INTEGER NOT NULL,
                  vector_json TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  PRIMARY KEY(record_id, model),
                  FOREIGN KEY(record_id) REFERENCES context_records(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS context_record_skill_links (
                  record_id TEXT NOT NULL,
                  skill_name TEXT NOT NULL,
                  reason TEXT,
                  confidence REAL NOT NULL DEFAULT 0.5,
                  source TEXT NOT NULL DEFAULT 'agent_observed',
                  created_at TEXT NOT NULL,
                  last_used_at TEXT,
                  PRIMARY KEY(record_id, skill_name),
                  FOREIGN KEY(record_id) REFERENCES context_records(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (1, utc_now()),
            )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (2, utc_now()),
            )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, utc_now()),
            )

    def schema_versions(self) -> list[int]:
        with self.connect() as conn:
            rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        return [int(row["version"]) for row in rows]

    def upsert_record(self, record: ContextRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO context_records (
                  id, kind, scope_user, scope_project, scope_repo, scope_profile,
                  title, summary, details, tags_json, entities_json, sources_json,
                  confidence, importance, trust_level, created_at, updated_at,
                  last_accessed_at, last_confirmed_at, expires_at, source_hash,
                  embedding_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  kind=excluded.kind,
                  scope_user=excluded.scope_user,
                  scope_project=excluded.scope_project,
                  scope_repo=excluded.scope_repo,
                  scope_profile=excluded.scope_profile,
                  title=excluded.title,
                  summary=excluded.summary,
                  details=excluded.details,
                  tags_json=excluded.tags_json,
                  entities_json=excluded.entities_json,
                  sources_json=excluded.sources_json,
                  confidence=excluded.confidence,
                  importance=excluded.importance,
                  trust_level=excluded.trust_level,
                  created_at=excluded.created_at,
                  updated_at=excluded.updated_at,
                  last_accessed_at=excluded.last_accessed_at,
                  last_confirmed_at=excluded.last_confirmed_at,
                  expires_at=excluded.expires_at,
                  source_hash=excluded.source_hash,
                  embedding_text=excluded.embedding_text
                """,
                _record_row(record),
            )
            self._replace_fts_row(conn, record)

    def get_record(self, record_id: str) -> ContextRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM context_records WHERE id = ?", (record_id,)
            ).fetchone()
        return _record_from_row(row) if row else None

    def list_records(self) -> list[ContextRecord]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM context_records ORDER BY id").fetchall()
        return [_record_from_row(row) for row in rows]

    def count_records(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM context_records").fetchone()
        return int(row["count"])

    def delete_record(self, record_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM context_records WHERE id = ?", (record_id,))
            conn.execute("DELETE FROM context_records_fts WHERE id = ?", (record_id,))
            conn.execute("DELETE FROM context_record_vectors WHERE record_id = ?", (record_id,))
            conn.execute("DELETE FROM context_record_skill_links WHERE record_id = ?", (record_id,))

    def upsert_skill_link(self, link: SkillLink) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO context_record_skill_links(
                  record_id, skill_name, reason, confidence, source, created_at, last_used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_id, skill_name) DO UPDATE SET
                  reason=excluded.reason,
                  confidence=excluded.confidence,
                  source=excluded.source,
                  created_at=excluded.created_at,
                  last_used_at=excluded.last_used_at
                """,
                _skill_link_row(link),
            )

    def list_skill_links(self, record_id: str) -> list[SkillLink]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM context_record_skill_links
                WHERE record_id = ?
                ORDER BY confidence DESC, skill_name
                """,
                (record_id,),
            ).fetchall()
        return [_skill_link_from_row(row) for row in rows]

    def replace_skill_links(self, record_id: str, links: list[SkillLink]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM context_record_skill_links WHERE record_id = ?", (record_id,))
            for link in links:
                conn.execute(
                    """
                    INSERT INTO context_record_skill_links(
                      record_id, skill_name, reason, confidence, source, created_at, last_used_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(record_id, skill_name) DO UPDATE SET
                      reason=excluded.reason,
                      confidence=excluded.confidence,
                      source=excluded.source,
                      created_at=excluded.created_at,
                      last_used_at=excluded.last_used_at
                    """,
                    _skill_link_row(link),
                )

    def delete_skill_link(self, record_id: str, skill_name: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM context_record_skill_links WHERE record_id = ? AND skill_name = ?",
                (record_id, skill_name),
            )

    def upsert_vector(
        self,
        *,
        record_id: str,
        model: str,
        dimensions: int,
        vector: list[float],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO context_record_vectors(record_id, model, dimensions, vector_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(record_id, model) DO UPDATE SET
                  dimensions=excluded.dimensions,
                  vector_json=excluded.vector_json,
                  updated_at=excluded.updated_at
                """,
                (
                    record_id,
                    model,
                    dimensions,
                    json.dumps(vector, separators=(",", ":")),
                    utc_now(),
                ),
            )

    def delete_vector(self, record_id: str, *, model: str | None = None) -> None:
        with self.connect() as conn:
            if model is None:
                conn.execute("DELETE FROM context_record_vectors WHERE record_id = ?", (record_id,))
            else:
                conn.execute(
                    "DELETE FROM context_record_vectors WHERE record_id = ? AND model = ?",
                    (record_id, model),
                )

    def list_vectors(self, *, model: str) -> list[dict[str, object]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT record_id, model, dimensions, vector_json, updated_at
                FROM context_record_vectors
                WHERE model = ?
                ORDER BY record_id
                """,
                (model,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_vectors(self, *, model: str | None = None) -> int:
        with self.connect() as conn:
            if model is None:
                row = conn.execute(
                    "SELECT COUNT(*) AS count FROM context_record_vectors"
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS count FROM context_record_vectors WHERE model = ?",
                    (model,),
                ).fetchone()
        return int(row["count"])

    def fts_search(self, query: str, *, limit: int) -> list[FtsHit]:
        fts_query = _fts_query(query)
        if not fts_query:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.*, bm25(context_records_fts) AS rank
                FROM context_records_fts
                JOIN context_records r ON r.id = context_records_fts.id
                WHERE context_records_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        return [FtsHit(record=_record_from_row(row), rank=float(row["rank"])) for row in rows]

    def log_retrieval_event(
        self,
        *,
        query: str,
        selected_ids: list[str],
        skipped_ids: list[str] | None = None,
        scores: dict[str, float] | None = None,
        max_chars: int | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO retrieval_events(
                  id, query, selected_ids_json, skipped_ids_json, scores_json, max_chars, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    query,
                    json.dumps(selected_ids, ensure_ascii=False),
                    json.dumps(skipped_ids or [], ensure_ascii=False),
                    json.dumps(scores or {}, ensure_ascii=False),
                    max_chars,
                    utc_now(),
                ),
            )

    def last_retrieval_event(self) -> dict[str, object] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM retrieval_events ORDER BY created_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def add_session_observation(
        self,
        *,
        session_id: str,
        turn_index: int,
        user_content: str,
        assistant_content: str,
        max_chars: int,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO session_observations(
                  id, session_id, turn_index, user_content, assistant_content, created_at, consolidated
                ) VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    uuid.uuid4().hex,
                    session_id,
                    turn_index,
                    sanitize_observation_text(user_content, max_chars=max_chars),
                    sanitize_observation_text(assistant_content, max_chars=max_chars),
                    utc_now(),
                ),
            )

    def list_unconsolidated_observations(self, session_id: str) -> list[dict[str, object]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM session_observations
                WHERE session_id = ? AND consolidated = 0
                ORDER BY turn_index, created_at
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_session_observations_consolidated(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE session_observations SET consolidated = 1 WHERE session_id = ?",
                (session_id,),
            )

    def _replace_fts_row(self, conn: sqlite3.Connection, record: ContextRecord) -> None:
        conn.execute("DELETE FROM context_records_fts WHERE id = ?", (record.id,))
        conn.execute(
            """
            INSERT INTO context_records_fts(id, title, summary, details, tags, entities)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.title,
                record.summary,
                record.details or "",
                _index_text(record.tags),
                _index_text(record.entities),
            ),
        )


def _record_row(record: ContextRecord) -> tuple[object, ...]:
    return (
        record.id,
        record.kind,
        record.scope_user,
        record.scope_project,
        record.scope_repo,
        record.scope_profile,
        record.title,
        record.summary,
        record.details,
        json.dumps(record.tags, ensure_ascii=False),
        json.dumps(record.entities, ensure_ascii=False),
        json.dumps([source.to_dict() for source in record.sources], ensure_ascii=False),
        record.confidence,
        record.importance,
        record.trust_level,
        record.created_at,
        record.updated_at,
        record.last_accessed_at,
        record.last_confirmed_at,
        record.expires_at,
        record.source_hash,
        record.embedding_text,
    )


def _record_from_row(row: sqlite3.Row) -> ContextRecord:
    return ContextRecord.from_dict(
        {
            "id": row["id"],
            "kind": row["kind"],
            "scope_user": row["scope_user"],
            "scope_project": row["scope_project"],
            "scope_repo": row["scope_repo"],
            "scope_profile": row["scope_profile"],
            "title": row["title"],
            "summary": row["summary"],
            "details": row["details"],
            "tags": json.loads(row["tags_json"]),
            "entities": json.loads(row["entities_json"]),
            "sources": [
                SourceRef.from_dict(item).to_dict() for item in json.loads(row["sources_json"])
            ],
            "confidence": row["confidence"],
            "importance": row["importance"],
            "trust_level": row["trust_level"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_accessed_at": row["last_accessed_at"],
            "last_confirmed_at": row["last_confirmed_at"],
            "expires_at": row["expires_at"],
            "source_hash": row["source_hash"],
            "embedding_text": row["embedding_text"],
        }
    )


def _skill_link_row(link: SkillLink) -> tuple[object, ...]:
    return (
        link.record_id,
        link.skill_name,
        link.reason,
        link.confidence,
        link.source,
        link.created_at,
        link.last_used_at,
    )


def _skill_link_from_row(row: sqlite3.Row) -> SkillLink:
    return SkillLink.from_dict(
        {
            "record_id": row["record_id"],
            "skill_name": row["skill_name"],
            "reason": row["reason"],
            "confidence": row["confidence"],
            "source": row["source"],
            "created_at": row["created_at"],
            "last_used_at": row["last_used_at"],
        }
    )


def _index_text(values: list[str]) -> str:
    import re

    expanded: list[str] = []
    for value in values:
        expanded.append(value)
        expanded.append(re.sub(r"[^\w]+", " ", value))
        expanded.append(value.replace("_", " ").replace("-", " ").replace(":", " "))
    return " ".join(expanded)


def _fts_query(query: str) -> str:
    import re

    tokens = re.findall(r"[\w:-]+", query.lower())
    return " OR ".join(f'"{token}"' for token in tokens[:20])
