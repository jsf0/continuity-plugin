from __future__ import annotations

from pathlib import Path

from continuity.extraction import extract_records_from_messages
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore
from continuity.tools import handle_add


def test_manual_write_enrichment_supports_metadata_anchor_retrieval(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    payload = handle_add(
        store,
        {
            "id": "r_openbsd_guard_proxy",
            "kind": "project_convention",
            "title": "OpenBSD guard-proxy deployment",
            "summary": "guard-proxy deployment uses tag:openbsd and rcctl restart.",
            "tags": ["deployment"],
            "entities": [],
            "trust_level": "explicit_user",
        },
    )
    assert payload["success"] is True

    debug = ContinuityRetriever(store).debug_search("openbsd rcctl guard-proxy", limit=3)

    assert debug["selected"]
    assert debug["selected"][0].record.id == "r_openbsd_guard_proxy"
    assert debug["selected"][0].tag_score > 0 or debug["selected"][0].entity_score > 0


def test_memory_marker_examples_do_not_enter_store_on_session_end() -> None:
    records = extract_records_from_messages(
        session_id="s1",
        messages=[
            {
                "role": "system",
                "content": "Prefer markers (`Remember:`, `Lesson learned:`, `Decision:`) before extraction.",
            },
            {
                "role": "assistant",
                "content": "Docs mention `Remember: I prefer examples` as syntax only.",
            },
        ],
    )

    assert records == []
