import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from continuity.models import ContextRecord
from continuity.reranking import RerankHit
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore


class RejectingReranker:
    def is_available(self):
        return True

    def rerank(self, query, records):
        return [RerankHit(record_id=record.id, score=0.01) for record in records]


class ScoreByIdReranker:
    def __init__(self, scores):
        self.scores = scores

    def is_available(self):
        return True

    def rerank(self, query, records):
        return [
            RerankHit(record_id=record.id, score=self.scores.get(record.id, 0.01))
            for record in records
        ]


def _record(
    record_id,
    summary,
    *,
    title=None,
    tags=None,
    entities=None,
    kind="user_preference",
    scope_project=None,
):
    return ContextRecord.new(
        id=record_id,
        kind=kind,
        title=title or record_id.replace("_", " "),
        summary=summary,
        scope_project=scope_project,
        tags=tags or [],
        entities=entities or [],
        confidence=0.9,
        importance=0.8,
        trust_level="explicit_user",
    )


def test_upsert_skips_association_edges_for_quality_review_required_record(tmp_path: Path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    good = _record(
        "good",
        "OpenBSD deployment uses rcctl restart.",
        tags=["openbsd", "deployment"],
        entities=["OpenBSD", "rcctl"],
    )
    weak = ContextRecord.from_dict(
        {
            **_record(
                "weak",
                "OpenBSD notes use rcctl restart.",
                tags=["openbsd"],
                entities=["OpenBSD"],
            ).to_dict(),
            "quality": {"review_required": True, "warnings": ["sparse_metadata"]},
        }
    )

    store.upsert_record(good)
    store.upsert_record(weak)

    assert store.list_association_edges("weak") == []


def test_store_persists_undirected_association_edges_and_caps_out_degree(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    center = _record("center", "central memory", tags=["center"])
    store.upsert_record(center)
    for index in range(4):
        store.upsert_record(_record(f"neighbor_{index}", f"neighbor {index}"))
        store.upsert_association_edge(
            "center",
            f"neighbor_{index}",
            strength=0.2 + index / 10,
            edge_type="test",
            out_degree_cap=3,
        )

    edges = store.list_association_edges("center")

    assert [edge.memory_id_b for edge in edges] == [
        "neighbor_3",
        "neighbor_2",
        "neighbor_1",
    ]
    assert all(0.0 <= edge.strength <= 1.0 for edge in edges)
    assert all(edge.edge_type == "test" for edge in edges)


def test_graph_spreading_adds_associative_neighbor_from_activation_only_seed(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    boat = _record(
        "boat_context",
        "User is considering trailerable sailboats and catamarans for lake sailing.",
        tags=["boat", "sailboat", "catamaran", "trailerable"],
        entities=["Hobie 16"],
    )
    truck = _record(
        "truck_context",
        "User has a 2018 Ford Raptor available for towing.",
        tags=["truck", "towing", "vehicle"],
        entities=["2018 Ford Raptor"],
    )
    store.upsert_record(boat)
    store.upsert_record(truck)
    store.upsert_association_edge(
        "boat_context",
        "truck_context",
        strength=0.95,
        edge_type="co_occurrence",
    )

    debug = ContinuityRetriever(
        store,
        reranker_backend=RejectingReranker(),
        reranker_min_score=0.15,
        association_enabled=True,
        association_activation_threshold=0.3,
        association_hop_decay=0.6,
        association_max_hops=2,
    ).debug_search("what boat sizes should I consider?", limit=5)

    selected_ids = [candidate.record.id for candidate in debug["selected"]]
    assert "boat_context" not in selected_ids
    assert "truck_context" in selected_ids

    truck_candidate = next(
        candidate for candidate in debug["selected"] if candidate.record.id == "truck_context"
    )
    assert truck_candidate.retrieval_role == "associative_neighbor"
    assert "associative_graph" in truck_candidate.reasons
    assert truck_candidate.activation >= 0.3
    assert debug["activation_trace"]["activation_seeds"][0]["record_id"] == "boat_context"
    assert debug["activation_trace"]["included_neighbors"][0]["record_id"] == "truck_context"


def test_memory_roadmap_query_does_not_activate_unrelated_retrieval_graph(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    corpus_design = _record(
        "corpus_design",
        "Continuity corpus ingestion roadmap uses SourceDocument to CandidateRecord review flow.",
        title="Corpus ingestion design roadmap",
        tags=["corpus-ingestion", "roadmap"],
        entities=["SourceDocument", "CandidateRecord"],
        kind="project_convention",
        scope_project="hermes-continuity-memory",
    )
    corpus_reminder = _record(
        "corpus_reminder",
        "Come back to continuity corpus ingestion work after stale cleanup and quality audit.",
        title="Corpus ingestion reminder",
        tags=["corpus-ingestion", "roadmap"],
        entities=["continuity ingestion"],
        kind="environment_fact",
        scope_project="hermes-continuity-memory",
    )
    retrieval_status = _record(
        "retrieval_status",
        "Continuity retrieval facet compatibility fixes changed association graph behavior.",
        title="Continuity retrieval fixes",
        tags=["continuity", "retrieval", "association-graph"],
        entities=["continuity plugin", "association graph"],
        kind="active_project_state",
        scope_project="hermes-continuity-memory",
    )
    boat_noise = _record(
        "boat_noise",
        "Boat towing regression used association graph rescue for Raptor context.",
        title="Continuity retrieval boat/towing regression result",
        tags=["continuity", "retrieval", "association-graph", "boat"],
        entities=["boat towing", "association graph"],
        kind="lesson_learned",
        scope_project="hermes-continuity-memory",
    )
    for record in [corpus_design, corpus_reminder, retrieval_status, boat_noise]:
        store.upsert_record(record, create_associations=False)
    store.upsert_association_edge(
        "retrieval_status",
        "boat_noise",
        strength=0.95,
        edge_type="entity_overlap",
    )

    debug = ContinuityRetriever(
        store,
        reranker_backend=ScoreByIdReranker({"corpus_design": 0.99, "corpus_reminder": 0.98}),
        reranker_min_score=0.15,
        association_enabled=True,
        association_activation_threshold=0.3,
        association_hop_decay=0.6,
        association_max_hops=2,
    ).debug_search("corpus ingestion roadmap continuity memory", limit=5)

    selected_ids = [candidate.record.id for candidate in debug["selected"]]
    assert selected_ids[:2] == ["corpus_design", "corpus_reminder"]
    assert "retrieval_status" not in selected_ids
    assert "boat_noise" not in selected_ids
    activation_seed_ids = {
        seed["record_id"] for seed in debug["activation_trace"]["activation_seeds"]
    }
    assert "retrieval_status" not in activation_seed_ids


def test_graph_spreading_respects_activation_threshold(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record("boat_context", "User is considering trailerable sailboats.", tags=["boat"])
    )
    store.upsert_record(_record("weak_neighbor", "Weakly associated memory.", tags=["unrelated"]))
    store.upsert_association_edge(
        "boat_context",
        "weak_neighbor",
        strength=0.2,
        edge_type="test",
    )

    debug = ContinuityRetriever(
        store,
        reranker_backend=RejectingReranker(),
        reranker_min_score=0.15,
        association_enabled=True,
        association_activation_threshold=0.3,
        association_hop_decay=0.6,
    ).debug_search("boat", limit=5)

    assert "weak_neighbor" not in [candidate.record.id for candidate in debug["selected"]]
    assert debug["activation_trace"]["cut_neighbors"][0]["record_id"] == "weak_neighbor"
    assert debug["activation_trace"]["cut_neighbors"][0]["reason"] == "below_activation_threshold"


def test_upserting_related_records_auto_creates_association_edges(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "sailboat",
            "User is shopping for trailerable sailboats.",
            tags=["boat", "sailing", "trailerable"],
            entities=["Hobie 16"],
        )
    )
    store.upsert_record(
        _record(
            "storage",
            "User likely has backyard storage for a trailerable catamaran.",
            tags=["boat", "storage", "trailerable"],
            entities=["catamaran"],
        )
    )

    edges = store.list_association_edges("sailboat")

    assert len(edges) == 1
    assert edges[0].memory_id_b == "storage"
    assert edges[0].strength >= 0.25
    assert edges[0].edge_type in {
        "entity_overlap",
        "tag_overlap",
        "semantic_similarity",
        "combined",
    }


def test_auto_edges_ignore_generic_mirror_titles_and_tags(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "mirror_user_boat",
            "User has a 2018 Ford Raptor for trailerable boats.",
            title="Hermes user memory",
            tags=["memory", "user", "preference"],
            entities=["2018 Ford Raptor"],
        )
    )
    store.upsert_record(
        _record(
            "mirror_user_hardware",
            "User has a Framework Desktop computer ordered.",
            title="Hermes user memory",
            tags=["memory", "user", "preference"],
            entities=["Framework Desktop"],
        )
    )

    assert store.list_association_edges("mirror_user_boat") == []


def test_memory_meta_query_suppresses_generic_mirror_records(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        ContextRecord.new(
            id="continuity_noise_tuning",
            kind="lesson_learned",
            title="Association graph noise tuning implemented",
            summary=(
                "Continuity memory retrieval noise tuning: meta queries about association graph, "
                "memory records, and retrieval should suppress generic mirror memories unless "
                "they have continuity-domain anchors."
            ),
            scope_project="hermes-continuity-memory",
            tags=["continuity", "retrieval", "association-graph", "noise"],
            entities=["continuity", "association graph", "retrieval"],
            confidence=0.9,
            importance=0.8,
        )
    )
    store.upsert_record(
        ContextRecord.new(
            id="framework_hardware",
            kind="environment_fact",
            title="Hermes global memory",
            summary=(
                "Framework Desktop plan: experiment with llama.cpp and evaluate local "
                "models as GPT-5.5 replacements for Hermes-agent."
            ),
            confidence=0.9,
            importance=0.75,
            trust_level="built_in_memory_mirror",
        )
    )
    store.upsert_record(
        ContextRecord.new(
            id="raptor_boat",
            kind="user_preference",
            title="Hermes user memory",
            summary="User has a 2018 Ford Raptor for trailerable boats.",
            confidence=0.9,
            importance=0.75,
            trust_level="built_in_memory_mirror",
        )
    )

    debug = ContinuityRetriever(store, association_enabled=True).debug_search(
        "how do we fix the remaining noise issue in memory records and association links?",
        scope_project="hermes-continuity-memory",
        limit=5,
    )

    selected_ids = [candidate.record.id for candidate in debug["selected"]]
    rejected = {candidate.record.id: candidate for candidate in debug["rejected"]}
    assert selected_ids == ["continuity_noise_tuning"]
    assert rejected["framework_hardware"].rejected_reason == "memory_meta_without_domain_anchor"
    assert rejected["raptor_boat"].rejected_reason == "memory_meta_without_domain_anchor"


def test_graph_does_not_pull_project_status_from_personal_query_via_tag_overlap(
    tmp_path,
):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "boat_context",
            "User is considering trailerable sailboats.",
            tags=["boat", "personal"],
        )
    )
    store.upsert_record(
        _record(
            "project_status",
            "guard-proxy current HEAD is clean after documentation cleanup.",
            tags=["personal", "status"],
            kind="active_project_state",
            scope_project="guard-proxy",
        )
    )
    store.upsert_association_edge(
        "boat_context",
        "project_status",
        strength=0.95,
        edge_type="tag_overlap",
    )

    debug = ContinuityRetriever(
        store,
        reranker_backend=RejectingReranker(),
        reranker_min_score=0.15,
        association_enabled=True,
        association_activation_threshold=0.3,
        association_hop_decay=0.6,
    ).debug_search("what boat sizes should I consider?", limit=5)

    assert "project_status" not in [candidate.record.id for candidate in debug["selected"]]
    assert any(
        cut["record_id"] == "project_status"
        and cut["reason"] == "personal_project_neighbor_mismatch"
        for cut in debug["activation_trace"]["cut_neighbors"]
    )


def test_association_edge_inventory_reports_endpoint_metadata(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(_record("left", "left boat context", tags=["boat"]))
    store.upsert_record(_record("right", "right towing context", tags=["towing"]))
    store.upsert_association_edge("left", "right", strength=0.7, edge_type="co_occurrence")

    inventory = store.list_association_edge_inventory(limit=10)

    assert inventory == [
        {
            "memory_id_a": "left",
            "memory_id_b": "right",
            "title_a": "left",
            "title_b": "right",
            "kind_a": "user_preference",
            "kind_b": "user_preference",
            "strength": 0.7,
            "edge_type": "co_occurrence",
            "last_reinforced_at": inventory[0]["last_reinforced_at"],
            "reinforcement_count": 1,
        }
    ]


def test_archiving_record_hides_association_edges_from_traversal_and_inventory(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(_record("active", "active boat context", tags=["boat"]))
    store.upsert_record(_record("stale", "stale towing context", tags=["towing"]))
    store.upsert_association_edge("active", "stale", strength=0.9, edge_type="co_occurrence")

    assert store.archive_record("stale", reason="superseded") is True

    assert store.list_association_edges("active") == []
    assert store.list_association_edge_inventory(limit=10) == []


def test_generic_elliptical_followup_does_not_activate_graph_neighbors(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "generic_status_seed",
            "guard-proxy is looking better but not quite finished; how about now is a generic status follow-up.",
            title="guard-proxy current status",
            tags=["status"],
            kind="active_project_state",
            scope_project="guard-proxy",
        )
    )
    store.upsert_record(
        _record(
            "guard_proxy_neighbor",
            "guard-proxy current HEAD has docs and working tree status updates.",
            title="guard-proxy current status after SPKI docs cleanup",
            tags=["guard-proxy", "status"],
            kind="active_project_state",
            scope_project="guard-proxy",
        )
    )
    store.upsert_association_edge(
        "generic_status_seed",
        "guard_proxy_neighbor",
        strength=0.95,
        edge_type="entity_overlap",
    )

    retriever = ContinuityRetriever(
        store,
        reranker_backend=RejectingReranker(),
        reranker_min_score=0.15,
        association_enabled=True,
        association_activation_threshold=0.3,
        association_hop_decay=0.6,
    )

    for query in (
        "ok so its looking better? Or not quite",
        "better now?",
        "how about now",
        "can you test and see if it's better now?",
    ):
        debug = retriever.debug_search(query, limit=5)

        assert debug["selected"] == []
        assert debug["activation_trace"]["activation_seeds"] == []

    debug = retriever.debug_search("ok so its looking better? Or not quite", limit=5)
    rejected = {candidate.record.id: candidate for candidate in debug["rejected"]}
    assert rejected["generic_status_seed"].rejected_reason == "low_information_direct_query"


def test_weak_status_tokens_do_not_seed_association_graph_without_strong_anchor(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "generic_project_status",
            "guard-proxy current state is fixed and working better after cleanup.",
            title="guard-proxy current status",
            tags=["status"],
            kind="active_project_state",
            scope_project="guard-proxy",
        )
    )
    store.upsert_record(
        _record(
            "guard_proxy_neighbor",
            "guard-proxy current HEAD has docs and working tree status updates.",
            title="guard-proxy current status after SPKI docs cleanup",
            tags=["guard-proxy", "status"],
            kind="active_project_state",
            scope_project="guard-proxy",
        )
    )
    store.upsert_association_edge(
        "generic_project_status",
        "guard_proxy_neighbor",
        strength=0.95,
        edge_type="entity_overlap",
    )

    debug = ContinuityRetriever(
        store,
        reranker_backend=RejectingReranker(),
        reranker_min_score=0.15,
        association_enabled=True,
        association_activation_threshold=0.3,
        association_hop_decay=0.6,
    ).debug_search("is the current status fixed and working better?", limit=5)

    assert debug["selected"] == []
    assert debug["activation_trace"]["activation_seeds"] == []
    rejected = {candidate.record.id: candidate for candidate in debug["rejected"]}
    assert rejected["generic_project_status"].rejected_reason == "low_information_direct_query"


def test_wrapper_query_direct_memory_does_not_let_unrelated_mirror_seed_graph(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "restart_preference",
            "When working on Hermes gateway/plugin fixes, defer gateway restarts until the end because restarts can kill the Discord session.",
            title="Gateway restart preference",
            tags=["gateway", "continuity"],
        )
    )
    store.upsert_record(
        ContextRecord.new(
            id="framework_boot",
            kind="environment_fact",
            title="Hermes global memory",
            summary="Framework Desktop Secure Boot failed until Secure Boot was disabled.",
            confidence=0.9,
            importance=0.75,
            trust_level="built_in_memory_mirror",
        )
    )
    store.upsert_record(
        ContextRecord.new(
            id="framework_hardware",
            kind="user_preference",
            title="Hermes user memory",
            summary="Hardware: Framework Desktop Ryzen AI Max 395 with 128GB RAM.",
            confidence=0.9,
            importance=0.75,
            trust_level="built_in_memory_mirror",
        )
    )
    store.upsert_association_edge(
        "framework_boot",
        "framework_hardware",
        strength=1.0,
        edge_type="entity_overlap",
    )

    debug = ContinuityRetriever(
        store,
        reranker_backend=RejectingReranker(),
        reranker_min_score=0.15,
        association_enabled=True,
        association_activation_threshold=0.3,
        association_hop_decay=0.6,
    ).debug_search(
        "ok keep going. Maybe hold off on restarting the gateway until the end since it kills your session",
        limit=5,
    )

    selected_ids = [candidate.record.id for candidate in debug["selected"]]
    rejected = {candidate.record.id: candidate for candidate in debug["rejected"]}
    assert "framework_hardware" not in selected_ids
    assert "framework_boot" not in [
        seed["record_id"] for seed in debug["activation_trace"]["activation_seeds"]
    ]
    assert rejected["framework_boot"].rejected_reason == "weak_anchor_activation_seed"


def test_strong_project_anchor_can_still_seed_association_graph(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "guard_proxy_seed",
            "guard-proxy current state has follow-up cleanup work.",
            title="guard-proxy current status",
            tags=["guard-proxy", "status"],
            kind="active_project_state",
            scope_project="guard-proxy",
        )
    )
    store.upsert_record(
        _record(
            "guard_proxy_neighbor",
            "guard-proxy detector deployment still needs production follow-up.",
            title="guard-proxy detector follow-up",
            tags=["guard-proxy", "detector"],
            kind="active_project_state",
            scope_project="guard-proxy",
        )
    )
    store.upsert_association_edge(
        "guard_proxy_seed",
        "guard_proxy_neighbor",
        strength=0.95,
        edge_type="entity_overlap",
    )

    debug = ContinuityRetriever(
        store,
        reranker_backend=RejectingReranker(),
        reranker_min_score=0.15,
        association_enabled=True,
        association_activation_threshold=0.3,
        association_hop_decay=0.6,
    ).debug_search("what is the guard-proxy status?", limit=5)

    selected_ids = [candidate.record.id for candidate in debug["selected"]]
    assert "guard_proxy_neighbor" in selected_ids
    assert debug["activation_trace"]["activation_seeds"][0]["record_id"] == "guard_proxy_seed"


def test_association_graph_meta_query_prefers_continuity_records_over_project_status(
    tmp_path,
):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "continuity_graph",
            "Continuity association-graph retrieval uses activation seeds and edges.",
            title="Continuity association graph design",
            tags=["continuity", "association-graph", "retrieval"],
            kind="lesson_learned",
            scope_project="hermes-continuity-memory",
        )
    )
    store.upsert_record(
        _record(
            "project_status",
            "guard-proxy current state has a clean working tree.",
            title="guard-proxy current status",
            tags=["project_status", "status"],
            kind="active_project_state",
            scope_project="guard-proxy",
        )
    )

    store.upsert_record(
        _record(
            "work_prefs",
            "Work prefs: methodical thorough correct; discuss changes before edits.",
            title="Hermes user memory",
            tags=["user_preference"],
        )
    )

    debug = ContinuityRetriever(store, association_enabled=True).debug_search(
        "how does the association graph work in its current state?", limit=3
    )

    assert [candidate.record.id for candidate in debug["selected"]] == ["continuity_graph"]


def test_personal_boat_query_does_not_match_project_status_on_generic_words(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "boat_context",
            "User has a 2018 Ford Raptor for trailerable boat towing.",
            tags=["boat", "towing", "trailerable", "vehicle"],
            entities=["2018 Ford Raptor"],
        )
    )
    store.upsert_record(
        _record(
            "project_status",
            "guard-proxy current HEAD has docs and working tree status updates.",
            title="guard-proxy current status",
            tags=["project_status", "status"],
            kind="active_project_state",
            scope_project="guard-proxy",
        )
    )

    debug = ContinuityRetriever(store, association_enabled=True).debug_search(
        "I'm thinking of buying a boat. what is my size limit based on towing capacity?",
        limit=5,
    )

    assert [candidate.record.id for candidate in debug["selected"]] == ["boat_context"]


def test_software_framework_query_does_not_pull_hardware_records_via_graph(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "framework_hardware_seed",
            "Framework Desktop Ryzen AI Max hardware arrived for local model experiments.",
            title="Framework Desktop hardware",
            tags=["hardware", "desktop"],
            entities=["Framework Desktop", "Ryzen AI Max"],
            kind="environment_fact",
        )
    )
    store.upsert_record(
        _record(
            "framework_hardware_neighbor",
            "Framework Desktop Secure Boot and BIOS settings affected OpenBSD USB boot.",
            title="Framework Desktop OpenBSD boot",
            tags=["hardware", "boot", "openbsd"],
            entities=["Framework Desktop", "OpenBSD", "BIOS"],
            kind="environment_fact",
        )
    )
    store.upsert_association_edge(
        "framework_hardware_seed",
        "framework_hardware_neighbor",
        strength=1.0,
        edge_type="entity_overlap",
    )

    debug = ContinuityRetriever(
        store,
        reranker_backend=RejectingReranker(),
        reranker_min_score=0.15,
        association_enabled=True,
        association_activation_threshold=0.3,
        association_hop_decay=0.6,
    ).debug_search("what API framework should we use?", limit=5)

    assert debug["selected"] == []
    assert debug["activation_trace"]["activation_seeds"] == []
    rejected = {candidate.record.id: candidate for candidate in debug["rejected"]}
    assert rejected["framework_hardware_seed"].rejected_reason in {
        "facet_incompatible_candidate",
        "facet_incompatible_activation_seed",
        "weak_anchor_activation_seed",
    }


def test_personal_work_preference_query_retrieves_work_preferences_not_project_neighbors(
    tmp_path,
):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "work_prefs",
            "Work prefs: methodical thorough correct; discuss changes before edits. Done means tests pass and docs are updated.",
            title="Hermes user memory",
            tags=["user_preference", "work_style"],
            kind="user_preference",
        )
    )
    store.upsert_record(
        _record(
            "continuity_status",
            "Continuity memory retrieval work changed association graph behavior.",
            title="Continuity memory status",
            tags=["continuity", "retrieval", "work"],
            kind="active_project_state",
            scope_project="hermes-continuity-memory",
        )
    )
    store.upsert_association_edge(
        "work_prefs",
        "continuity_status",
        strength=0.95,
        edge_type="tag_overlap",
    )

    debug = ContinuityRetriever(
        store,
        reranker_backend=RejectingReranker(),
        reranker_min_score=0.15,
        association_enabled=True,
        association_activation_threshold=0.3,
        association_hop_decay=0.6,
    ).debug_search("how do I prefer you handle big code changes?", limit=5)

    selected_ids = [candidate.record.id for candidate in debug["selected"]]
    assert selected_ids == ["work_prefs"]


def test_non_memory_query_does_not_match_continuity_eval_record_that_quotes_it(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "continuity_eval",
            "Regression eval found `what API framework should we use?` must not retrieve Framework Desktop hardware memories.",
            title="Continuity retrieval eval",
            tags=["continuity", "retrieval", "regression"],
            kind="active_project_state",
            scope_project="hermes-continuity-memory",
        )
    )

    debug = ContinuityRetriever(store, association_enabled=True).debug_search(
        "what API framework should we use?", limit=5
    )

    assert debug["selected"] == []
    rejected = {candidate.record.id: candidate for candidate in debug["rejected"]}
    assert rejected["continuity_eval"].rejected_reason == "memory_system_record_without_meta_query"
