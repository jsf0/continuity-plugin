"""Regression tests for incremental vector indexing (skip-if-text-unchanged).

Gateway startup previously re-embedded the ENTIRE corpus on every restart via
index_records(); with slow neural embedders (mxbai-embed-large ~0.7s/doc) that
scales linearly into minutes. upsert() now records a sha256 of the embedding
text and skips the model call when the stored vector was built from identical
text.
"""

import pytest

from continuity.embeddings import SQLiteHashVectorBackend, index_records
from continuity.models import ContextRecord
from continuity.store import ContinuityStore


def _record(rid: str, text: str) -> ContextRecord:
    return ContextRecord(
        id=rid,
        kind="environment_fact",
        title=text[:40],
        summary=text,
        details=text,
        embedding_text=text,
    )


@pytest.fixture()
def store(tmp_path):
    s = ContinuityStore(tmp_path / "test.db")
    s.migrate()
    return s


class CountingBackend(SQLiteHashVectorBackend):
    """Same skip logic as production backends, but counts embeddings."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.embed_calls = 0

    def upsert(self, record_id: str, text: str) -> None:
        from continuity.embeddings import _embedding_text_hash

        if self.store.vector_text_hash(record_id, model=self.model) == _embedding_text_hash(text):
            return
        self.embed_calls += 1
        super().upsert(record_id, text)


def test_index_records_skips_unchanged_text(store):
    backend = CountingBackend(store)
    records = [_record("r1", "alpha text"), _record("r2", "beta text")]

    index_records(backend, records)
    assert backend.embed_calls == 2
    assert store.count_vectors(model=backend.model) == 2

    # Second pass with identical texts: nothing re-embedded.
    index_records(backend, records)
    assert backend.embed_calls == 2
    assert store.count_vectors(model=backend.model) == 2


def test_index_records_reembeds_changed_text_only(store):
    backend = CountingBackend(store)
    records = [_record("r1", "alpha text"), _record("r2", "beta text")]
    index_records(backend, records)

    records[1] = _record("r2", "beta text UPDATED")
    index_records(backend, records)
    assert backend.embed_calls == 3  # only r2 re-embedded
    assert store.count_vectors(model=backend.model) == 2


def test_hash_lookup_missing_vector_returns_none(store):
    assert store.vector_text_hash("nope", model="hash-v1") is None


def test_upsert_stores_text_hash(store):
    backend = SQLiteHashVectorBackend(store)
    backend.upsert("r1", "some text")
    assert store.vector_text_hash("r1", model=backend.model) is not None
    # delete clears it
    backend.delete("r1")
    assert store.vector_text_hash("r1", model=backend.model) is None


def test_migrate_adds_text_hash_column_to_existing_db(tmp_path):
    # Build a DB without the column, then migrate — column must appear.
    import sqlite3

    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE context_record_vectors (
          record_id TEXT NOT NULL,
          model TEXT NOT NULL,
          dimensions INTEGER NOT NULL,
          vector_json TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(record_id, model)
        );
        """
    )
    conn.execute(
        "INSERT INTO context_record_vectors VALUES ('r1','hash-v1',4,'[1.0]', '2026-01-01')"
    )
    conn.commit()
    conn.close()

    s = ContinuityStore(db)
    s.migrate()
    backend = SQLiteHashVectorBackend(s)
    # Existing row (no hash) gets re-embedded because hash is NULL.
    backend.upsert("r1", "some text")
    assert s.vector_text_hash("r1", model="hash-v1") is not None
    # And the legacy vector survives the column addition.
    assert s.count_vectors(model="hash-v1") == 1
