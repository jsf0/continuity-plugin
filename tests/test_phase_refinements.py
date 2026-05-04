import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from continuity.__init__ import _format_prefetch_context
from continuity.models import ContextRecord
from continuity.project import ProjectContext, build_project_capsule
from continuity.reranking import RerankHit
from continuity.retrieval import ContinuityRetriever
from continuity.staleness import find_stale_candidates
from continuity.store import ContinuityStore


class HighReranker:
    def is_available(self):
        return True

    def rerank(self, query, records):
        return [RerankHit(record_id=record.id, score=0.95) for record in records]


class RejectingReranker:
    def is_available(self):
        return True

    def rerank(self, query, records):
        return [RerankHit(record_id=record.id, score=0.01) for record in records]


def _record(record_id, summary, **kwargs):
    status = kwargs.pop("status", "active")
    record = ContextRecord.new(
        id=record_id,
        kind=kwargs.pop("kind", "lesson_learned"),
        title=kwargs.pop("title", record_id.replace("_", " ")),
        summary=summary,
        confidence=kwargs.pop("confidence", 0.9),
        importance=kwargs.pop("importance", 0.8),
        trust_level=kwargs.pop("trust_level", "agent_observed"),
        **kwargs,
    )
    if status != "active":
        data = record.to_dict()
        data["status"] = status
        record = ContextRecord.from_dict(data)
    return record


def test_low_information_direct_query_rejects_record_that_only_matches_wrapper_phrase(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "status_wrapper",
            "Live tests mention the wrapper phrase can you test and see if it is better now.",
            tags=["status"],
            scope_project="hermes-continuity-memory",
        )
    )

    debug = ContinuityRetriever(
        store,
        reranker_backend=HighReranker(),
        reranker_min_score=0.15,
    ).debug_search("can you test and see if it's better now?", limit=5)

    assert [candidate.record.id for candidate in debug["selected"]] == []
    rejected = {candidate.record.id: candidate for candidate in debug["rejected"]}
    assert rejected["status_wrapper"].rejected_reason == "low_information_direct_query"


def test_low_information_gate_allows_query_with_continuity_domain_anchor(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "continuity_status",
            "Continuity memory retrieval is improved but still needs noise tuning.",
            tags=["continuity", "retrieval", "noise"],
            entities=["continuity", "reranker"],
            scope_project="hermes-continuity-memory",
        )
    )

    debug = ContinuityRetriever(
        store,
        reranker_backend=HighReranker(),
        reranker_min_score=0.15,
    ).debug_search("is continuity memory fixed now?", limit=5)

    assert [candidate.record.id for candidate in debug["selected"]] == ["continuity_status"]


def test_auto_edges_require_meaningful_overlap_not_generic_mirror_boilerplate(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    mirror_a = _record(
        "mirror_a",
        "Framework Desktop arrived for llama.cpp experiments.",
        title="Hermes global memory",
        kind="environment_fact",
        tags=["built_in_memory", "memory_target:memory", "environment_fact"],
        entities=["memory target memory", "Hermes memory"],
        trust_level="built_in_memory_mirror",
    )
    mirror_b = _record(
        "mirror_b",
        "guard-proxy status update after docs cleanup.",
        title="Hermes global memory",
        kind="environment_fact",
        tags=["built_in_memory", "memory_target:memory", "environment_fact"],
        entities=["memory target memory", "Hermes memory"],
        trust_level="built_in_memory_mirror",
    )

    store.upsert_record(mirror_a)
    store.upsert_record(mirror_b)

    assert store.list_association_edges("mirror_a") == []


def test_project_capsule_excludes_global_user_preferences_archived_and_long_unrelated_records():
    project = ProjectContext(project_id="git:repo", root=Path("/tmp/repo"), display_name="repo")
    records = [
        _record(
            "repo_lesson",
            "Repo-specific pitfall about continuity retrieval.",
            kind="lesson_learned",
            scope_project="repo",
        ),
        _record(
            "global_user_pref",
            "User has unrelated personal hardware preferences.",
            kind="user_preference",
            scope_project=None,
        ),
        _record(
            "root_decision",
            "Long unrelated guard-proxy decision. " * 80,
            kind="decision",
            scope_project="root",
        ),
        _record(
            "archived_repo_fact",
            "Archived repo fact should not be present.",
            kind="project_convention",
            scope_project="repo",
            status="archived",
        ),
    ]

    capsule = build_project_capsule(project, records)

    assert "Repo-specific pitfall" in capsule.summary
    assert "personal hardware" not in capsule.summary
    assert "guard-proxy" not in capsule.summary
    assert "Archived repo fact" not in capsule.summary
    assert len(capsule.summary) < 1200
    assert [source.id for source in capsule.sources] == ["repo_lesson"]


def test_prune_flags_session_extracted_skill_dump_misclassified_as_user_preference():
    bad = _record(
        "bad_skill_dump",
        "## RAG / Vector DB Guidance\n"
        + "context_record_association_edges embedding_text reranker " * 20,
        kind="user_preference",
        title="user preference: `, `Lesson learned:`, `Decision:`) before broad LLM extraction",
        entities=[f"entity_{index}" for index in range(80)],
        trust_level="session_extracted",
    )

    stale = find_stale_candidates([bad], limit=10)

    assert stale[0].record_id == "bad_skill_dump"
    assert "misclassified extracted procedural/skill dump" in stale[0].reason


def test_prefetch_rendering_separates_direct_and_associated_context():
    direct = _record(
        "direct",
        "Continuity direct fact.",
        kind="lesson_learned",
        scope_project="hermes-continuity-memory",
    )
    associated = _record("associated", "Lower-confidence associated fact.")
    hits = [
        type(
            "Hit",
            (),
            {
                "record": direct,
                "score": 1.0,
                "skill_links": (),
                "retrieval_role": "direct_seed",
                "activation": 0.9,
            },
        )(),
        type(
            "Hit",
            (),
            {
                "record": associated,
                "score": 0.7,
                "skill_links": (),
                "retrieval_role": "associative_neighbor",
                "activation": 0.4,
            },
        )(),
    ]

    output, included = _format_prefetch_context(
        hits,
        max_chars=2000,
        include_sources=False,
        include_scores=False,
    )

    assert len(included) == 2
    assert "Directly relevant continuity memory:" in output
    assert "Associated continuity context (lower confidence):" in output
    assert "role=direct" in output
    assert "role=associated" in output
