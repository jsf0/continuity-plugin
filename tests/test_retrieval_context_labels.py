from __future__ import annotations

from pathlib import Path

from continuity.context_labels import ContextLabelSet, context_to_mapping
from continuity.models import ContextRecord
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore


def make_record(record_id: str, *, label_key: str, label_value: str, summary: str) -> ContextRecord:
    return ContextRecord.new(
        id=record_id,
        kind="artifact_summary",
        title="ifconfig alias syntax",
        summary=summary,
        details="ifconfig alias syntax differs by context partition.",
        tags=["ifconfig", "alias", label_value],
        entities=["ifconfig"],
        confidence=0.9,
        importance=0.8,
        trust_level="corpus_distilled",
        quality={
            "context": context_to_mapping(
                ContextLabelSet(
                    labels={label_key: label_value},
                    partition_keys=frozenset({label_key}),
                    identity_keys=frozenset({"command"}),
                    collision_risk="high",
                )
            )
        },
    )


def seeded_store(tmp_path: Path, records: list[ContextRecord]) -> ContinuityStore:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    for record in records:
        store.upsert_record(record, create_associations=False)
    return store


def ids_for_search(
    store: ContinuityStore,
    query_context: dict[str, object] | None = None,
    *,
    comparison_intent: bool = False,
) -> list[str]:
    return [
        hit.record.id
        for hit in ContinuityRetriever(store, association_enabled=False).search(
            "ifconfig alias syntax",
            query_context=query_context,
            comparison_intent=comparison_intent,
            limit=10,
        )
    ]


def test_query_context_selects_matching_partition_and_rejects_conflict(tmp_path: Path) -> None:
    openbsd = make_record(
        "ifconfig_openbsd",
        label_key="os",
        label_value="openbsd",
        summary="OpenBSD ifconfig alias syntax uses alias address on the interface.",
    )
    linux = make_record(
        "ifconfig_linux",
        label_key="os",
        label_value="linux",
        summary="Linux ifconfig alias syntax commonly uses a colon-suffixed interface.",
    )
    store = seeded_store(tmp_path, [openbsd, linux])

    assert ids_for_search(store, {"labels": {"os": "openbsd"}, "partition_keys": ["os"]}) == [
        "ifconfig_openbsd"
    ]
    assert ids_for_search(store, {"labels": {"os": "linux"}, "partition_keys": ["os"]}) == [
        "ifconfig_linux"
    ]

    debug = ContinuityRetriever(store, association_enabled=False).debug_search(
        "ifconfig alias syntax",
        query_context={"labels": {"os": "openbsd"}, "partition_keys": ["os"]},
        limit=10,
    )
    rejected = {candidate.record.id: candidate.rejected_reason for candidate in debug["rejected"]}
    assert rejected["ifconfig_linux"] == "context_label_conflict:os"


def test_missing_query_context_withholds_high_collision_records(tmp_path: Path) -> None:
    store = seeded_store(
        tmp_path,
        [
            make_record(
                "ifconfig_openbsd",
                label_key="os",
                label_value="openbsd",
                summary="OpenBSD ifconfig alias syntax uses alias address.",
            ),
            make_record(
                "ifconfig_linux",
                label_key="os",
                label_value="linux",
                summary="Linux ifconfig alias syntax uses a colon-suffixed interface.",
            ),
        ],
    )

    debug = ContinuityRetriever(store, association_enabled=False).debug_search(
        "ifconfig alias syntax", limit=10
    )

    assert debug["selected"] == []
    assert {candidate.rejected_reason for candidate in debug["rejected"]} == {
        "missing_partition_context:os"
    }


def test_comparison_intent_allows_conflicting_partitions(tmp_path: Path) -> None:
    store = seeded_store(
        tmp_path,
        [
            make_record(
                "ifconfig_openbsd",
                label_key="os",
                label_value="openbsd",
                summary="OpenBSD ifconfig alias syntax uses alias address.",
            ),
            make_record(
                "ifconfig_linux",
                label_key="os",
                label_value="linux",
                summary="Linux ifconfig alias syntax uses a colon-suffixed interface.",
            ),
        ],
    )

    ids = ids_for_search(store, comparison_intent=True)

    assert ids == ["ifconfig_linux", "ifconfig_openbsd"]


def test_same_generic_gate_handles_customer_and_language_partitions(tmp_path: Path) -> None:
    records = [
        make_record(
            "rollout_acme",
            label_key="customer",
            label_value="acme",
            summary="Acme rollout plan requires canary approval before broad rollout.",
        ),
        make_record(
            "rollout_globex",
            label_key="customer",
            label_value="globex",
            summary="Globex rollout plan requires maintenance-window approval.",
        ),
        make_record(
            "map_rust",
            label_key="language",
            label_value="rust",
            summary="Rust map documentation describes Iterator::map with closures.",
        ),
        make_record(
            "map_python",
            label_key="language",
            label_value="python",
            summary="Python map documentation describes applying a callable to iterables.",
        ),
    ]
    store = seeded_store(tmp_path, records)
    retriever = ContinuityRetriever(store, association_enabled=False)

    customer_hits = retriever.search(
        "rollout plan approval",
        query_context={"labels": {"customer": "acme"}, "partition_keys": ["customer"]},
        limit=10,
    )
    language_hits = retriever.search(
        "map documentation callable closure",
        query_context={"labels": {"language": "python"}, "partition_keys": ["language"]},
        limit=10,
    )

    assert [hit.record.id for hit in customer_hits] == ["rollout_acme"]
    assert [hit.record.id for hit in language_hits] == ["map_python"]


def test_association_graph_cuts_conflicting_context_neighbor(tmp_path: Path) -> None:
    openbsd = make_record(
        "ifconfig_openbsd",
        label_key="os",
        label_value="openbsd",
        summary="OpenBSD ifconfig alias syntax uses alias address.",
    )
    linux = make_record(
        "ifconfig_linux",
        label_key="os",
        label_value="linux",
        summary="Linux details are reachable only through graph activation.",
    )
    store = seeded_store(tmp_path, [openbsd, linux])
    store.upsert_association_edge(
        "ifconfig_openbsd", "ifconfig_linux", strength=1.0, edge_type="semantic_similarity"
    )

    debug = ContinuityRetriever(store).debug_search(
        "ifconfig alias openbsd syntax",
        query_context={"labels": {"os": "openbsd"}, "partition_keys": ["os"]},
        limit=10,
    )

    assert [candidate.record.id for candidate in debug["selected"]] == ["ifconfig_openbsd"]
    assert any(
        cut["record_id"] == "ifconfig_linux" and cut["reason"] == "context_label_conflict"
        for cut in debug["activation_trace"]["cut_neighbors"]
    )
