"""Retrieval and scoring for continuity memory records."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .config import RetrievalGateConfig
from .context_labels import (
    ContextCompatibility,
    ContextLabelSet,
    compare_contexts,
    context_from_mapping,
    context_from_record,
    context_to_mapping,
    has_comparison_intent,
)
from .dynamic_expansion import propose_expansion_terms
from .embeddings import VectorBackend
from .models import ContextRecord, SkillLink
from .reranking import RerankerBackend
from .store import ContinuityStore
from .vocabulary import CorpusTermStats

SCOPE_BONUS = 1.0
CAPSULE_SCOPE_BONUS = 2.0
TAG_BONUS = 1.5
ENTITY_BONUS = 1.75
TEXT_MATCH_BONUS = 0.35
CONFIDENCE_WEIGHT = 0.5
IMPORTANCE_WEIGHT = 0.5
FTS_WEIGHT = 1.0
VECTOR_WEIGHT = 3.0
MIN_BASE_RELEVANCE = 0.35
MIN_VECTOR_RELEVANCE = 0.05
# Vector retrieval is a supplement, not authority.  If a candidate has no
# lexical/tag/entity/FTS anchor at all, require a stronger semantic score so
# generic status/debug queries do not pull unrelated high-confidence memories.
MIN_VECTOR_ONLY_RELEVANCE = 2.75
TRUST_PENALTIES = {
    "remote_untrusted": 1.0,
}

ALIASES = {
    # Keep only language/tooling-normalization aliases here.  Domain expansion is
    # derived dynamically from stored record metadata in dynamic_expansion.py.
    "subagent": {"delegate_task", "delegation", "worker"},
    "subagents": {"delegate_task", "delegation", "worker"},
    "agent": {"subagent"},
    "association": {"association-graph", "continuity", "retrieval"},
    "graph": {"association-graph", "continuity", "retrieval"},
    "worker": {"subagent"},
    "timed": {"timeout"},
    "timeout": {"timeout", "hung", "stuck"},
    "timeouts": {"timeout"},
}

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "again",
        "are",
        "be",
        "based",
        "buying",
        "can",
        "current",
        "do",
        "did",
        "doing",
        "for",
        "fix",
        "fixed",
        "fixes",
        "figure",
        "how",
        "i",
        "in",
        "is",
        "it",
        "kinds",
        "m",
        "me",
        "my",
        "of",
        "on",
        "out",
        "should",
        "state",
        "the",
        "that",
        "thing",
        "thinking",
        "to",
        "trying",
        "usability",
        "usable",
        "was",
        "we",
        "what",
        "when",
        "why",
        "with",
        "without",
    }
)

LOW_INFORMATION_ACTIVATION_TOKENS = frozenset(
    {
        "about",
        "almost",
        "better",
        "can",
        "check",
        "done",
        "fixed",
        "how",
        "if",
        "improved",
        "its",
        "looking",
        "need",
        "needs",
        "not",
        "now",
        "ok",
        "or",
        "quite",
        "s",
        "see",
        "so",
        "still",
        "test",
        "worse",
        "yet",
        "you",
    }
)
WEAK_ANCHOR_TOKENS = (
    STOPWORDS
    | LOW_INFORMATION_ACTIVATION_TOKENS
    | frozenset(
        {
            "check",
            "cleanup",
            "continue",
            "current",
            "done",
            "issue",
            "problem",
            "project",
            "s",
            "state",
            "statu",
            "status",
            "update",
            "updates",
            "work",
            "working",
        }
    )
)
PERSONAL_QUERY_RAW_TERMS = frozenset({"i", "me", "my", "mine", "myself"})
PERSONAL_KINDS = frozenset({"user_preference", "user_fact", "personal_setup", "vehicle_fact"})
PROJECT_STATUS_KINDS = frozenset({"active_project_state", "project_convention"})
GENERIC_ASSOCIATION_EDGE_TYPES = frozenset({"tag_overlap", "semantic_similarity"})
GENERIC_PROJECT_SCOPES = frozenset({"root", ".", ""})
BOILERPLATE_MIRROR_TITLES = frozenset({"hermes global memory", "hermes user memory"})
MEMORY_META_INTENT_TOKENS = frozenset(
    {
        "association",
        "association-graph",
        "continuity",
        "embedding",
        "memory-provider",
        "noise",
        "reranker",
        "retrieval",
        "vector",
    }
)
MEMORY_META_GENERIC_TOKENS = frozenset({"memory", "record"})
MEMORY_META_ACTION_TOKENS = frozenset({"issue", "link", "noise", "retrieval"})
MEMORY_META_RECORD_ANCHORS = MEMORY_META_INTENT_TOKENS | frozenset(
    {"memory-system", "memory-provider"}
)
RETRIEVAL_HELPFULNESS_TOKENS = frozenset({"help", "helpful", "useful"})
RETRIEVAL_HELPFULNESS_CONTEXT_TOKENS = frozenset(
    {"query", "answer", "response", "previous", "prior", "this"}
)

PREFERENCE_QUERY_TOKENS = frozenset(
    # "handle" deliberately excluded: "how do we handle X" is a procedural
    # question, not a personal-preference query.  Treating it as preference
    # intent tagged such queries with the personal_preference facet and made
    # software-project records facet-incompatible (observed: firmware-update
    # queries rejecting the project's own design records).
    {"prefer", "preference", "prefs", "style", "work_style"}
)

# First-person ownership/attribute questions ("what car do I drive?",
# "what phone do I use", "which OS am I running").  These queries carry a
# strong personal anchor but often share zero lexical tokens with the
# personal record that answers them, so the weak-vector-only gate would
# otherwise reject the correct answer.
OWNERSHIP_QUERY_TOKENS = frozenset(
    {
        "own",
        "drive",
        "riding",
        "ride",
        "carry",
        "wear",
        "use",
        "using",
        "run",
        "running",
        "play",
        "playing",
        "fly",
        "flying",
        "daily",
    }
)

FACET_TOKEN_MAP = {
    "software_project": frozenset(
        {
            "api",
            "repo",
            "code",
            "library",
            "package",
            "service",
            "web",
            "cli",
            "plugin",
            "python",
            "test",
            "docs",
            "routing",
            "middleware",
        }
    ),
    "personal_hardware": frozenset(
        {
            "hardware",
            "desktop",
            "laptop",
            "gpu",
            "cpu",
            "nvme",
            "ram",
            "bios",
            "boot",
            "usb",
            "workstation",
        }
    ),
    "memory_system": MEMORY_META_INTENT_TOKENS
    | frozenset({"memory", "record", "prefetch", "provider", "association-graph"}),
    "vehicle_towing": frozenset(
        {"vehicle", "truck", "van", "towing", "tow", "trailer", "hitch", "camper"}
    ),
    "personal_preference": PREFERENCE_QUERY_TOKENS
    | frozenset({"methodical", "thorough", "correct", "discuss", "done", "work_style"}),
    "model_eval": frozenset({"model", "llm", "programming", "eval"}),
    "devops_security": frozenset({"deployment", "security", "detector"}),
}

INCOMPATIBLE_FACET_PAIRS = frozenset(
    {
        frozenset({"software_project", "personal_hardware"}),
        frozenset({"memory_system", "personal_hardware"}),
        frozenset({"memory_system", "vehicle_towing"}),
        frozenset({"personal_preference", "software_project"}),
        frozenset({"personal_preference", "memory_system"}),
        frozenset({"personal_preference", "personal_hardware"}),
        frozenset({"personal_preference", "vehicle_towing"}),
    }
)


@dataclass(frozen=True)
class RetrievalHit:
    """Ranked retrieval result."""

    record: ContextRecord
    score: float
    reasons: tuple[str, ...]
    skill_links: tuple[SkillLink, ...] = ()
    retrieval_role: str = "direct_seed"
    activation: float = 0.0
    activation_trace: tuple[dict[str, object], ...] = ()


@dataclass
class CandidateScore:
    """Debuggable score components for a candidate record."""

    record: ContextRecord
    fts_score: float = 0.0
    vector_score: float = 0.0
    tag_score: float = 0.0
    entity_score: float = 0.0
    text_score: float = 0.0
    scope_score: float = 0.0
    metadata_boost: float = 0.0
    reranker_score: float = 0.0
    reranker_boost: float = 0.0
    association_score: float = 0.0
    penalties: float = 0.0
    reasons: list[str] = field(default_factory=list)
    rejected_reason: str | None = None
    retrieval_role: str = "direct_seed"
    activation: float = 0.0
    activation_trace: list[dict[str, object]] = field(default_factory=list)

    @property
    def base_relevance(self) -> float:
        return (
            self.fts_score
            + self.vector_score
            + self.tag_score
            + self.entity_score
            + self.text_score
        )

    @property
    def total(self) -> float:
        return (
            self.base_relevance
            + self.scope_score
            + self.metadata_boost
            + self.reranker_boost
            + self.association_score
            - self.penalties
        )


class ContinuityRetriever:
    """Hybrid FTS + metadata + optional vector retriever for continuity records."""

    def __init__(
        self,
        store: ContinuityStore,
        *,
        vector_backend: VectorBackend | None = None,
        reranker_backend: RerankerBackend | None = None,
        reranker_min_score: float = 0.15,
        reranker_weight: float = 2.0,
        reranker_top_k: int = 20,
        association_enabled: bool = True,
        association_edge_creation_threshold: float = 0.25,
        association_out_degree_cap: int = 20,
        association_hop_decay: float = 0.6,
        association_activation_threshold: float = 0.3,
        association_max_hops: int = 2,
        gate_config: RetrievalGateConfig | None = None,
    ) -> None:
        self.store = store
        self.vector_backend = vector_backend
        self.reranker_backend = reranker_backend
        self.reranker_min_score = max(0.0, min(1.0, reranker_min_score))
        self.reranker_weight = max(0.0, reranker_weight)
        self.reranker_top_k = max(1, reranker_top_k)
        self.association_enabled = association_enabled
        self.association_edge_creation_threshold = max(
            0.0, min(1.0, association_edge_creation_threshold)
        )
        self.association_out_degree_cap = max(1, association_out_degree_cap)
        self.association_hop_decay = max(0.0, min(1.0, association_hop_decay))
        self.association_activation_threshold = max(0.0, min(1.0, association_activation_threshold))
        self.association_max_hops = max(1, association_max_hops)
        self.gate_config = gate_config or RetrievalGateConfig()

    def search(
        self,
        query: str,
        *,
        scope_project: object = None,
        limit: int = 5,
        include_stale: bool = False,
        query_context: ContextLabelSet | dict[str, object] | None = None,
        comparison_intent: bool = False,
    ) -> list[RetrievalHit]:
        debug = self.debug_search(
            query,
            scope_project=scope_project,
            limit=limit,
            include_stale=include_stale,
            query_context=query_context,
            comparison_intent=comparison_intent,
        )
        hits = [
            RetrievalHit(
                record=candidate.record,
                score=candidate.total,
                reasons=tuple(candidate.reasons),
                skill_links=tuple(self.store.list_skill_links(candidate.record.id)),
                retrieval_role=candidate.retrieval_role,
                activation=candidate.activation,
                activation_trace=tuple(candidate.activation_trace),
            )
            for candidate in debug["selected"]
        ]
        return hits[:limit]

    def debug_search(
        self,
        query: str,
        *,
        scope_project: object = None,
        limit: int = 5,
        include_stale: bool = False,
        query_context: ContextLabelSet | dict[str, object] | None = None,
        comparison_intent: bool = False,
    ) -> dict[str, object]:
        tokens = _query_tokens(query)
        expanded_tokens = _expand_tokens(tokens)
        raw_tokens = _raw_query_tokens(query)
        effective_query_context = (
            query_context
            if isinstance(query_context, ContextLabelSet)
            else context_from_mapping(query_context or {})
        )
        effective_query_context = _infer_query_context_from_record_labels(
            effective_query_context,
            expanded_tokens,
            self.store.list_records(),
            query=query,
            include_stale=include_stale,
        )
        effective_comparison_intent = comparison_intent or has_comparison_intent(query)
        personal_query = bool(raw_tokens & PERSONAL_QUERY_RAW_TERMS)
        preference_query = _is_preference_query(expanded_tokens, personal_query=personal_query)
        ownership_query = personal_query and bool(expanded_tokens & OWNERSHIP_QUERY_TOKENS)
        memory_meta_query = _is_memory_meta_query(expanded_tokens)
        retrieval_helpfulness_meta_query = _is_retrieval_helpfulness_meta_query(raw_tokens)
        if retrieval_helpfulness_meta_query:
            return {
                "query": query,
                "query_context": context_to_mapping(effective_query_context),
                "comparison_intent": effective_comparison_intent,
                "tokens": sorted(tokens),
                "expanded_tokens": sorted(expanded_tokens),
                "dynamic_expansion": [],
                "selected": [],
                "rejected": [],
                "activation_trace": {
                    "direct_seeds": [],
                    "activation_seeds": [],
                    "edges_fired": [],
                    "included_neighbors": [],
                    "cut_neighbors": [],
                },
            }
        exact_context_bypass_ids = _exact_context_partition_bypass_record_ids(
            self.store.list_records(), raw_tokens, include_stale=include_stale
        )
        query_facets = _facets_for_tokens(expanded_tokens)
        candidates: dict[str, CandidateScore] = {}
        effective_scope = str(scope_project) if scope_project else None

        fts_query = " ".join(sorted(expanded_tokens))
        if fts_query:
            for hit in self.store.fts_search(fts_query, limit=max(limit * 6, 30)):
                if not include_stale and _is_inactive_or_expired(hit.record):
                    continue
                candidate = candidates.setdefault(hit.record.id, CandidateScore(hit.record))
                candidate.fts_score += max(0.0, 1.0 / (1.0 + abs(hit.rank))) * FTS_WEIGHT
                if "fts" not in candidate.reasons:
                    candidate.reasons.append("fts")

        if self.vector_backend and self.vector_backend.is_available():
            for vector_hit in self.vector_backend.search(query, limit=max(limit * 6, 30)):
                record = self.store.get_record(vector_hit.record_id)
                if record is None:
                    self.vector_backend.delete(vector_hit.record_id)
                    continue
                if not include_stale and _is_inactive_or_expired(record):
                    continue
                vector_score = max(0.0, vector_hit.score)
                if vector_score < self.gate_config.min_vector_relevance:
                    continue
                candidate = candidates.setdefault(record.id, CandidateScore(record))
                candidate.vector_score += vector_score * VECTOR_WEIGHT
                candidate.reasons.append("vector")

        for record in self.store.list_records():
            if not include_stale and _is_inactive_or_expired(record):
                continue
            candidate = candidates.setdefault(record.id, CandidateScore(record))
            _apply_metadata_score(candidate, expanded_tokens)
            _apply_exact_identifier_score(candidate, raw_tokens)
            if candidate.base_relevance <= 0:
                candidates.pop(record.id, None)
                continue

        dynamic_expansion = []
        if not _is_low_information_direct_query(expanded_tokens):
            expansion_candidates = [
                candidate
                for candidate in candidates.values()
                if not _facets_incompatible(query_facets, _facets_for_record(candidate.record))
                and not _memory_system_record_without_meta_query(
                    candidate.record, query_facets, _facets_for_record(candidate.record)
                )
                and _candidate_matches_expansion_topic(candidate, expanded_tokens, tokens)
            ]
            dynamic_expansion = propose_expansion_terms(
                expanded_tokens,
                expansion_candidates,
                self.store,
                CorpusTermStats.from_records(
                    record
                    for record in self.store.list_records()
                    if include_stale or not _is_inactive_or_expired(record)
                ),
            )
        expansion_tokens = {term.term for term in dynamic_expansion}
        if expansion_tokens:
            new_tokens = expansion_tokens - expanded_tokens
            expanded_tokens |= expansion_tokens
            query_facets = _facets_for_tokens(expanded_tokens)
            fts_query = " ".join(sorted(new_tokens))
            if fts_query:
                for hit in self.store.fts_search(fts_query, limit=max(limit * 6, 30)):
                    if not include_stale and _is_inactive_or_expired(hit.record):
                        continue
                    candidate = candidates.setdefault(hit.record.id, CandidateScore(hit.record))
                    candidate.fts_score += max(0.0, 1.0 / (1.0 + abs(hit.rank))) * FTS_WEIGHT
                    if "fts" not in candidate.reasons:
                        candidate.reasons.append("fts")
            for record in self.store.list_records():
                if not include_stale and _is_inactive_or_expired(record):
                    continue
                candidate = candidates.setdefault(record.id, CandidateScore(record))
                before = candidate.base_relevance
                _apply_metadata_score(candidate, new_tokens)
                _apply_exact_identifier_score(candidate, raw_tokens)
                if before <= 0 and candidate.base_relevance <= 0:
                    candidates.pop(record.id, None)
                    continue

        selected: list[CandidateScore] = []
        rejected: list[CandidateScore] = []
        for candidate in candidates.values():
            if candidate.base_relevance < self.gate_config.min_base_relevance:
                candidate.rejected_reason = "below_min_base_relevance"
                rejected.append(candidate)
                continue
            if self.gate_config.weak_vector_only and _is_weak_vector_only_candidate(
                candidate, self.gate_config
            ):
                # First-person ownership/attribute questions ("what car do I
                # drive?") legitimately reach personal records through vector
                # similarity alone: the query noun often never appears in the
                # record text.  Relax the vector-only gate for personal-kind
                # records on such queries, at half the normal threshold.
                if (
                    ownership_query
                    and candidate.record.kind in PERSONAL_KINDS
                    and candidate.vector_score >= self.gate_config.min_vector_only_relevance * 0.5
                ):
                    candidate.reasons.append("ownership_query_vector_rescue")
                else:
                    candidate.rejected_reason = "weak_vector_only_without_anchor"
                    rejected.append(candidate)
                    continue
            _apply_scope_score(candidate, expanded_tokens, effective_scope)
            _apply_boosts_and_penalties(candidate, personal_query=personal_query)
            if (
                self.gate_config.memory_meta
                and retrieval_helpfulness_meta_query
                and candidate.record.kind in PROJECT_STATUS_KINDS
            ):
                candidate.rejected_reason = "retrieval_helpfulness_meta_query_requires_events"
                rejected.append(candidate)
                continue
            if (
                self.gate_config.memory_meta
                and memory_meta_query
                and not _memory_meta_record_allowed(
                    candidate.record, expanded_tokens, effective_scope
                )
            ):
                candidate.rejected_reason = "memory_meta_without_domain_anchor"
                rejected.append(candidate)
                continue
            if (
                self.gate_config.memory_meta
                and memory_meta_query
                and not _candidate_matches_expansion_topic(candidate, expanded_tokens, tokens)
            ):
                candidate.rejected_reason = "memory_meta_topic_mismatch"
                rejected.append(candidate)
                continue
            record_facets = _facets_for_record(candidate.record)
            if self.gate_config.memory_meta and _memory_system_record_without_meta_query(
                candidate.record, query_facets, record_facets
            ):
                candidate.rejected_reason = "memory_system_record_without_meta_query"
                rejected.append(candidate)
                continue
            if self.gate_config.facet_compatibility and _facets_incompatible(
                query_facets, record_facets
            ):
                candidate.rejected_reason = "facet_incompatible_candidate"
                rejected.append(candidate)
                continue
            if (
                self.gate_config.project_status_anchor
                and candidate.record.kind == "active_project_state"
            ):
                strong_tokens = expanded_tokens - WEAK_ANCHOR_TOKENS
                metadata_tokens = _record_metadata_tokens(candidate.record) | _query_tokens(
                    candidate.record.scope_project or ""
                )
                if strong_tokens and not (strong_tokens & metadata_tokens):
                    candidate.rejected_reason = "weak_project_status_candidate"
                    rejected.append(candidate)
                    continue
            if (
                self.gate_config.personal_project
                and personal_query
                and candidate.record.kind in PROJECT_STATUS_KINDS
            ):
                strong_tokens = expanded_tokens - WEAK_ANCHOR_TOKENS - {"personal"}
                if not (strong_tokens & _record_anchor_tokens(candidate.record)):
                    candidate.rejected_reason = "personal_project_candidate_mismatch"
                    rejected.append(candidate)
                    continue
            if (
                self.gate_config.low_information
                and _is_low_information_direct_query(expanded_tokens)
                and not (
                    _direct_low_information_candidate_allowed(
                        candidate.record, expanded_tokens, effective_scope
                    )
                )
            ):
                candidate.rejected_reason = "low_information_direct_query"
                rejected.append(candidate)
                continue
            if not _apply_context_compatibility(
                candidate,
                effective_query_context,
                comparison_intent=effective_comparison_intent,
                allow_missing_partition=candidate.record.id in exact_context_bypass_ids,
            ):
                rejected.append(candidate)
                continue
            if candidate.total <= 0:
                candidate.rejected_reason = "non_positive_total_score"
                rejected.append(candidate)
                continue
            selected.append(candidate)

        self._apply_reranker(query, selected, rejected)
        if preference_query:
            _restore_preference_candidates(selected, rejected, expanded_tokens)
        activation_trace = self._apply_association_graph(
            selected,
            rejected,
            expanded_tokens=expanded_tokens,
            query_tokens=tokens,
            query_facets=query_facets,
            query_context=effective_query_context,
            comparison_intent=effective_comparison_intent,
            personal_query=personal_query,
            include_stale=include_stale,
        )
        selected.sort(key=_candidate_selection_sort_key)
        selected = _suppress_duplicate_families(selected)
        rejected.sort(key=lambda candidate: (-candidate.total, candidate.record.id))
        return {
            "query": query,
            "query_context": context_to_mapping(effective_query_context),
            "comparison_intent": effective_comparison_intent,
            "tokens": sorted(tokens),
            "expanded_tokens": sorted(expanded_tokens),
            "dynamic_expansion": [term.to_dict() for term in dynamic_expansion],
            "selected": selected[:limit],
            "rejected": rejected,
            "activation_trace": activation_trace,
        }

    def _apply_reranker(
        self,
        query: str,
        selected: list[CandidateScore],
        rejected: list[CandidateScore],
    ) -> None:
        if (
            not selected
            or self.reranker_backend is None
            or not self.reranker_backend.is_available()
        ):
            return
        selected.sort(key=lambda candidate: (-candidate.total, candidate.record.id))
        rerank_pool = selected[: self.reranker_top_k]
        scores = {
            hit.record_id: hit.score
            for hit in self.reranker_backend.rerank(
                query, [candidate.record for candidate in rerank_pool]
            )
        }
        for candidate in list(rerank_pool):
            if candidate.record.id not in scores:
                continue
            candidate.reranker_score = max(0.0, min(1.0, scores[candidate.record.id]))
            candidate.reranker_boost = candidate.reranker_score * self.reranker_weight
            candidate.reasons.append("reranker")
            if candidate.reranker_score < self.reranker_min_score:
                if _reranker_rejection_overridden_by_exact_context_identifier(candidate):
                    candidate.reasons.append("exact_context_identifier_reranker_bypass")
                    continue
                if (
                    self.gate_config.strong_personal_anchor_reranker_bypass
                    and _reranker_rejection_overridden_by_strong_personal_anchor(candidate)
                ):
                    candidate.reasons.append("strong_personal_anchor")
                    continue
                candidate.rejected_reason = "below_min_reranker_score"
                selected.remove(candidate)
                rejected.append(candidate)

    def _apply_association_graph(
        self,
        selected: list[CandidateScore],
        rejected: list[CandidateScore],
        *,
        expanded_tokens: set[str],
        query_tokens: set[str],
        query_facets: set[str],
        query_context: ContextLabelSet,
        comparison_intent: bool,
        personal_query: bool,
        include_stale: bool,
    ) -> dict[str, object]:
        trace: dict[str, object] = {
            "direct_seeds": [],
            "activation_seeds": [],
            "edges_fired": [],
            "included_neighbors": [],
            "cut_neighbors": [],
        }
        if not self.association_enabled:
            return trace

        candidates_by_id = {candidate.record.id: candidate for candidate in [*selected, *rejected]}
        selected_ids = {candidate.record.id for candidate in selected}
        frontier: list[tuple[str, float, int, str]] = []

        for candidate in selected:
            candidate.retrieval_role = "direct_seed"
            activation = _candidate_activation(candidate)
            candidate.activation = max(candidate.activation, activation)
            frontier.append((candidate.record.id, activation, 0, candidate.record.id))
            trace["direct_seeds"].append(
                {"record_id": candidate.record.id, "activation": activation}
            )

        for candidate in rejected:
            if not _is_activation_only_seed(candidate, self.gate_config):
                continue
            if self.gate_config.low_information and _is_low_information_activation_query(
                expanded_tokens
            ):
                candidate.rejected_reason = "low_information_query_activation_seed"
                continue
            if self.gate_config.activation_anchor and not _has_strong_activation_anchor(
                candidate, expanded_tokens, query_tokens
            ):
                candidate.rejected_reason = "weak_anchor_activation_seed"
                continue
            if self.gate_config.facet_compatibility and _facets_incompatible(
                query_facets, _facets_for_record(candidate.record)
            ):
                candidate.rejected_reason = "facet_incompatible_activation_seed"
                continue
            activation = _candidate_activation(candidate)
            if activation < self.association_activation_threshold:
                continue
            candidate.retrieval_role = "activation_seed"
            candidate.activation = max(candidate.activation, activation)
            frontier.append((candidate.record.id, activation, 0, candidate.record.id))
            trace["activation_seeds"].append(
                {
                    "record_id": candidate.record.id,
                    "activation": activation,
                    "rejected_reason": candidate.rejected_reason,
                }
            )

        best_activation: dict[str, float] = {}
        best_trace: dict[str, list[dict[str, object]]] = {}
        while frontier:
            source_id, source_activation, hop, root_seed_id = frontier.pop(0)
            if hop >= self.association_max_hops:
                continue
            for edge in self.store.list_association_edges(source_id):
                neighbor_id = edge.memory_id_b
                neighbor_activation = min(
                    1.0, source_activation * edge.strength * self.association_hop_decay
                )
                edge_event = {
                    "from": source_id,
                    "to": neighbor_id,
                    "root_seed_id": root_seed_id,
                    "hop": hop + 1,
                    "edge_type": edge.edge_type,
                    "edge_strength": edge.strength,
                    "source_activation": source_activation,
                    "activation": neighbor_activation,
                }
                trace["edges_fired"].append(edge_event)
                if neighbor_activation < self.association_activation_threshold:
                    trace["cut_neighbors"].append(
                        {
                            **edge_event,
                            "record_id": neighbor_id,
                            "reason": "below_activation_threshold",
                        }
                    )
                    continue
                if neighbor_id == root_seed_id:
                    trace["cut_neighbors"].append(
                        {
                            **edge_event,
                            "record_id": neighbor_id,
                            "reason": "root_seed_already_active",
                        }
                    )
                    continue
                if neighbor_activation <= best_activation.get(neighbor_id, 0.0):
                    continue
                record = self.store.get_record(neighbor_id)
                if record is None:
                    trace["cut_neighbors"].append(
                        {
                            **edge_event,
                            "record_id": neighbor_id,
                            "reason": "missing_record",
                        }
                    )
                    continue
                if not include_stale and _is_inactive_or_expired(record):
                    trace["cut_neighbors"].append(
                        {
                            **edge_event,
                            "record_id": neighbor_id,
                            "reason": "inactive_or_expired",
                        }
                    )
                    continue
                neighbor_allowed, cut_reason = _association_neighbor_allowed(
                    root_seed=self.store.get_record(root_seed_id),
                    source=self.store.get_record(source_id),
                    neighbor=record,
                    edge_type=edge.edge_type,
                    expanded_tokens=expanded_tokens,
                    query_facets=query_facets,
                    query_context=query_context,
                    comparison_intent=comparison_intent,
                    personal_query=personal_query,
                    gate_config=self.gate_config,
                )
                if not neighbor_allowed:
                    trace["cut_neighbors"].append(
                        {
                            **edge_event,
                            "record_id": neighbor_id,
                            "reason": cut_reason,
                        }
                    )
                    continue
                best_activation[neighbor_id] = neighbor_activation
                best_trace[neighbor_id] = [*best_trace.get(source_id, []), edge_event]
                frontier.append((neighbor_id, neighbor_activation, hop + 1, root_seed_id))

        rejected_by_id = {candidate.record.id: candidate for candidate in rejected}
        for neighbor_id, activation in sorted(
            best_activation.items(), key=lambda item: (-item[1], item[0])
        ):
            if neighbor_id in selected_ids:
                continue
            candidate = candidates_by_id.get(neighbor_id) or rejected_by_id.get(neighbor_id)
            if candidate is None:
                record = self.store.get_record(neighbor_id)
                if record is None:
                    continue
                candidate = CandidateScore(record)
                candidates_by_id[neighbor_id] = candidate
            if candidate in rejected:
                rejected.remove(candidate)
                candidate.rejected_reason = None
            candidate.retrieval_role = "associative_neighbor"
            candidate.activation = activation
            candidate.activation_trace = best_trace.get(neighbor_id, [])
            if any(
                edge.get("edge_type") == "source_reference" for edge in candidate.activation_trace
            ):
                if any(
                    reason.startswith("context_label_conflict:") for reason in candidate.reasons
                ):
                    candidate.metadata_boost = 0.0
                else:
                    candidate.metadata_boost = max(0.0, candidate.metadata_boost)
                candidate.reasons.append("source_reference_context_bridge")
            candidate.association_score = activation
            candidate.reasons.append("associative_graph")
            selected.append(candidate)
            selected_ids.add(neighbor_id)
            trace["included_neighbors"].append(
                {
                    "record_id": neighbor_id,
                    "activation": activation,
                    "trace": candidate.activation_trace,
                }
            )
        return trace


def _infer_query_context_from_record_labels(
    query_context: ContextLabelSet,
    tokens: set[str],
    records: list[ContextRecord],
    *,
    query: str = "",
    include_stale: bool,
) -> ContextLabelSet:
    """Infer explicit query context from label values present in the query text.

    Corpus-ingested records can require partition labels such as ``os=openbsd``.
    If the user literally says "OpenBSD" but no caller-provided query_context is
    available, treating that token as a context label preserves the high-collision
    safety gate while still surfacing exact document matches.
    """

    inferred: dict[str, str] = dict(query_context.labels)
    query_lower = query.casefold()
    explicit_keys = set(query_context.labels)
    ambiguous_keys: set[str] = set()
    partition_keys: set[str] = set(query_context.partition_keys)
    identity_keys: set[str] = set(query_context.identity_keys)
    for record in records:
        if not include_stale and _is_inactive_or_expired(record):
            continue
        record_context = context_from_record(record)
        for key, value in record_context.labels.items():
            value_matches_query = value in tokens or (
                any(char in value for char in ".-_/:") and value.casefold() in query_lower
            )
            if key in explicit_keys or not value_matches_query:
                continue
            previous = inferred.get(key)
            if previous is not None and previous != value:
                previous_specificity = _label_value_query_specificity(previous, query_lower, tokens)
                value_specificity = _label_value_query_specificity(value, query_lower, tokens)
                if value_specificity > previous_specificity:
                    inferred[key] = value
                elif value_specificity == previous_specificity:
                    ambiguous_keys.add(key)
                continue
            inferred[key] = value
            if key in record_context.partition_keys:
                partition_keys.add(key)
            if key in record_context.identity_keys:
                identity_keys.add(key)

    for key in ambiguous_keys - explicit_keys:
        inferred.pop(key, None)
        partition_keys.discard(key)
        identity_keys.discard(key)

    if (
        "command" in inferred
        and "manual_section" not in inferred
        and {"file", "format"}.issubset(tokens)
    ):
        inferred["manual_section"] = "5"
        identity_keys.add("manual_section")

    if inferred == query_context.labels:
        return query_context

    return ContextLabelSet(
        labels=inferred,
        partition_keys=frozenset(key for key in partition_keys if key in inferred),
        soft_keys=query_context.soft_keys,
        identity_keys=frozenset(key for key in identity_keys if key in inferred),
        collision_risk=query_context.collision_risk,
    )


def _candidate_selection_sort_key(candidate: CandidateScore) -> tuple[int, float, str]:
    exact_identity_match = (
        candidate.retrieval_role == "direct_seed"
        and not any(reason.startswith("context_label_conflict:") for reason in candidate.reasons)
        and (
            "context_label_match:command" in candidate.reasons
            or "context_label_match:manual_section" in candidate.reasons
        )
    )
    return (-int(exact_identity_match), -candidate.total, candidate.record.id)


def _label_value_query_specificity(value: str, query_lower: str, tokens: set[str]) -> int:
    score = 0
    if value in tokens:
        score = max(score, len(value))
    if any(char in value for char in ".-_/:") and value.casefold() in query_lower:
        score = max(score, 1000 + len(value))
    return score


def _apply_context_compatibility(
    candidate: CandidateScore,
    query_context: ContextLabelSet,
    *,
    comparison_intent: bool,
    allow_missing_partition: bool = False,
) -> bool:
    compatibility = compare_contexts(
        query_context,
        context_from_record(candidate.record),
        comparison_intent=comparison_intent,
        allow_missing_partition=allow_missing_partition,
    )
    candidate.metadata_boost += compatibility.score_adjustment
    for reason in compatibility.reasons:
        if reason not in candidate.reasons:
            candidate.reasons.append(reason)
    if compatibility.hard_conflict and not compatibility.comparison_allowed:
        conflict_key = next(iter(sorted(compatibility.conflicts)), "context")
        candidate.rejected_reason = f"context_label_conflict:{conflict_key}"
        return False
    if compatibility.missing_required_partition and not compatibility.comparison_allowed:
        missing_key = next(iter(sorted(compatibility.missing_query_keys)), "context")
        candidate.rejected_reason = f"missing_partition_context:{missing_key}"
        return False
    if compatibility.missing_required_record and not compatibility.comparison_allowed:
        missing_key = next(iter(sorted(compatibility.missing_record_keys)), "context")
        candidate.rejected_reason = f"missing_record_context:{missing_key}"
        return False
    return True


def _association_context_allowed(
    *,
    root_seed: ContextRecord | None,
    neighbor: ContextRecord,
    edge_type: str,
    query_context: ContextLabelSet,
    comparison_intent: bool,
) -> tuple[bool, str]:
    effective_query_context = query_context
    root_context = context_from_record(root_seed) if root_seed is not None else ContextLabelSet()
    if not effective_query_context.labels and root_context.labels:
        effective_query_context = root_context
    compatibility = compare_contexts(
        effective_query_context,
        context_from_record(neighbor),
        comparison_intent=comparison_intent,
        allow_missing_partition=bool(root_context.labels),
    )
    if _source_reference_context_bridge_allowed(
        edge_type=edge_type,
        query_context=effective_query_context,
        record_context=context_from_record(neighbor),
        compatibility=compatibility,
    ):
        return True, "allowed_source_reference_context_bridge"
    if compatibility.hard_conflict and not compatibility.comparison_allowed:
        return False, "context_label_conflict"
    if compatibility.missing_required_partition and not compatibility.comparison_allowed:
        return False, "missing_partition_context"
    if compatibility.missing_required_record and not compatibility.comparison_allowed:
        return False, "missing_record_context"
    return True, "allowed"


def _source_reference_context_bridge_allowed(
    *,
    edge_type: str,
    query_context: ContextLabelSet,
    record_context: ContextLabelSet,
    compatibility: ContextCompatibility,
) -> bool:
    """Allow explicit source-reference edges to cross identity labels safely.

    A source reference such as a manpage SEE ALSO link intentionally points from
    one artifact identity to another.  It should not be rejected merely because
    the root record's identity labels (for example command/manual_section) differ
    from the neighbor's identity labels.  Partition labels (for example os,
    customer, language) remain hard boundaries.
    """

    if edge_type != "source_reference" or compatibility.comparison_allowed:
        return False
    conflict_keys = set(compatibility.conflicts)
    partition_conflicts = conflict_keys & (
        query_context.partition_keys | record_context.partition_keys
    )
    if partition_conflicts:
        return False
    if compatibility.missing_required_partition:
        return False
    identity_conflicts = conflict_keys & (
        query_context.identity_keys | record_context.identity_keys
    )
    return bool(identity_conflicts) and identity_conflicts == conflict_keys


def _association_neighbor_allowed(
    *,
    root_seed: ContextRecord | None,
    source: ContextRecord | None,
    neighbor: ContextRecord,
    edge_type: str,
    expanded_tokens: set[str],
    query_facets: set[str],
    query_context: ContextLabelSet,
    comparison_intent: bool,
    personal_query: bool,
    gate_config: RetrievalGateConfig,
) -> tuple[bool, str]:
    """Gate graph-expanded neighbors so broad edges do not pollute context."""
    context_allowed, context_cut_reason = _association_context_allowed(
        root_seed=root_seed,
        neighbor=neighbor,
        edge_type=edge_type,
        query_context=query_context,
        comparison_intent=comparison_intent,
    )
    if not context_allowed:
        return False, context_cut_reason
    if gate_config.facet_compatibility and _facets_incompatible(
        query_facets, _facets_for_record(neighbor)
    ):
        return False, "facet_incompatible_associative_neighbor"
    if gate_config.memory_meta and _memory_system_record_without_meta_query(
        neighbor, query_facets, _facets_for_record(neighbor)
    ):
        return False, "memory_system_neighbor_without_meta_query"
    if neighbor.trust_level == "built_in_memory_mirror" and not (
        expanded_tokens & _record_metadata_tokens(neighbor)
    ):
        return False, "mirror_neighbor_without_metadata_anchor"
    if (
        gate_config.personal_project
        and personal_query
        and neighbor.kind in PROJECT_STATUS_KINDS
        and edge_type in GENERIC_ASSOCIATION_EDGE_TYPES
    ):
        neighbor_tokens = _record_anchor_tokens(neighbor)
        if not expanded_tokens & neighbor_tokens:
            return False, "personal_project_neighbor_mismatch"
    if (
        gate_config.personal_project
        and root_seed is not None
        and root_seed.kind in PERSONAL_KINDS
        and neighbor.kind in PROJECT_STATUS_KINDS
        and edge_type in GENERIC_ASSOCIATION_EDGE_TYPES
    ):
        neighbor_tokens = _record_anchor_tokens(neighbor)
        if not expanded_tokens & neighbor_tokens:
            return False, "personal_project_neighbor_mismatch"
    if (
        gate_config.personal_project
        and source is not None
        and source.kind in PROJECT_STATUS_KINDS
        and neighbor.kind in PERSONAL_KINDS
        and edge_type in GENERIC_ASSOCIATION_EDGE_TYPES
    ):
        neighbor_tokens = _record_anchor_tokens(neighbor)
        if not expanded_tokens & neighbor_tokens:
            return False, "project_personal_neighbor_mismatch"
    return True, "allowed"


def _record_anchor_tokens(record: ContextRecord) -> set[str]:
    return _record_metadata_tokens(record) | _record_text_tokens(record)


def _record_metadata_tokens(record: ContextRecord) -> set[str]:
    tokens: set[str] = set()
    for tag in record.tags:
        tokens.update(_query_tokens(tag))
        normalized = _normalize_token(tag)
        if normalized:
            tokens.add(normalized)
    for entity in record.entities:
        tokens.update(_query_tokens(entity))
        normalized = _normalize_token(entity)
        if normalized:
            tokens.add(normalized)
    return tokens


def _reranker_rejection_overridden_by_exact_context_identifier(candidate: CandidateScore) -> bool:
    """Preserve exact context-label hits when a generic reranker underscores them.

    Section-like corpus records can be terse, so a cross-encoder may score some
    exact command/manpage chunks below threshold even though context labels prove
    they are the requested identifier.  Keep only strong exact context matches;
    ambiguous text/entity hits still obey the reranker.
    """

    return (
        "exact_context_identifier" in candidate.reasons
        and "context_label_match:command" in candidate.reasons
        and candidate.entity_score >= ENTITY_BONUS
    )


def _reranker_rejection_overridden_by_strong_personal_anchor(
    candidate: CandidateScore,
) -> bool:
    """Keep strongly anchored personal records even when a generic reranker is cold.

    Local cross-encoders often under-score short personal-context records for
    implicit first-person questions (for example vehicle/towing setup).  Strong
    tag/entity matches are safer direct anchors than relying entirely on graph
    rescue, but require multiple metadata anchors so a single incidental tag does
    not bypass the reranker.
    """
    if candidate.record.kind not in PERSONAL_KINDS:
        return False
    return candidate.entity_score >= ENTITY_BONUS or candidate.tag_score >= (TAG_BONUS * 2)


def _candidate_activation(candidate: CandidateScore) -> float:
    """Normalize direct or anchored candidate strength for graph spreading."""
    if (
        candidate.reranker_score > 0
        and candidate.rejected_reason != "below_min_reranker_score"
        and "strong_personal_anchor" not in candidate.reasons
    ):
        return max(0.0, min(1.0, candidate.reranker_score))
    return max(0.0, min(1.0, candidate.total / 5.0))


def _is_activation_only_seed(candidate: CandidateScore, gate_config: RetrievalGateConfig) -> bool:
    """Allow strong anchored candidates rejected by direct reranking to light the graph."""
    if candidate.rejected_reason != "below_min_reranker_score":
        return False
    has_anchor = any(
        score > 0
        for score in (
            candidate.fts_score,
            candidate.tag_score,
            candidate.entity_score,
            candidate.text_score,
        )
    )
    return has_anchor and candidate.base_relevance >= gate_config.min_base_relevance


def _is_low_information_activation_query(tokens: set[str]) -> bool:
    """Return true for vague follow-ups that should not seed graph spreading.

    Association activation seeds are intentionally allowed to bypass direct-answer
    reranking for implicit context rescue, but short elliptical follow-ups like
    "ok so it's looking better?" have no durable domain/project/entity anchor.
    Let direct retrieval/reranking answer such queries if it can; otherwise do not
    fan out through old association edges.
    """
    return bool(tokens) and not (tokens - LOW_INFORMATION_ACTIVATION_TOKENS)


def _is_low_information_direct_query(tokens: set[str]) -> bool:
    """Return true for vague status/wrapper queries with no durable anchor.

    Direct candidates can otherwise pass reranking merely because a memory record
    mentions a regression phrase like "can you test and see if it's better now".
    Treat these like activation seeds: no strong query anchor, no context.
    """
    return bool(tokens) and not (tokens - WEAK_ANCHOR_TOKENS)


def _direct_low_information_candidate_allowed(
    record: ContextRecord, tokens: set[str], scope_project: str | None
) -> bool:
    if tokens & MEMORY_META_INTENT_TOKENS:
        return _memory_meta_record_allowed(record, tokens, scope_project)
    strong_tokens = tokens - WEAK_ANCHOR_TOKENS
    if not strong_tokens:
        return False
    record_tags = {_normalize_token(tag) for tag in record.tags}
    record_entities = {_normalize_token(entity) for entity in record.entities}
    project_tokens = _query_tokens(record.scope_project or "")
    return bool(strong_tokens & (record_tags | record_entities | project_tokens))


def _candidate_matches_expansion_topic(
    candidate: CandidateScore, expanded_tokens: set[str], query_tokens: set[str]
) -> bool:
    topic_tokens = _activation_anchor_tokens(expanded_tokens, query_tokens)
    if not topic_tokens:
        return True
    return bool(topic_tokens & _record_anchor_tokens(candidate.record))


def _has_strong_activation_anchor(
    candidate: CandidateScore, expanded_tokens: set[str], query_tokens: set[str]
) -> bool:
    """Require non-generic query anchors before a rejected candidate seeds graph spread."""
    strong_tokens = _activation_anchor_tokens(expanded_tokens, query_tokens)
    if not strong_tokens:
        return False
    record = candidate.record
    record_tags = {_normalize_token(tag) for tag in record.tags}
    record_entities = {_normalize_token(entity) for entity in record.entities}
    project_tokens = _query_tokens(record.scope_project or "")
    if strong_tokens & (record_tags | record_entities | project_tokens):
        return True
    if record.trust_level == "built_in_memory_mirror":
        # Mirrored stock memories often contain broad prose.  Let them be
        # directly retrieved when reranking agrees, but do not let incidental
        # text matches like "until" or "session" seed graph spreading into
        # unrelated mirrored hardware/project memories.
        return False
    return bool(candidate.text_score > 0 and strong_tokens & _record_text_tokens(record))


def _activation_anchor_tokens(expanded_tokens: set[str], query_tokens: set[str]) -> set[str]:
    """Return the query anchors allowed to start graph spreading.

    Dynamic expansion may add memory-system terms from loosely related rejected
    records.  If the user's original query contains a more specific non-memory
    topic (for example a roadmap/corpus term), require activation-only seeds to
    match that topic instead of generic continuity/retrieval terms.
    """

    query_strong = query_tokens - WEAK_ANCHOR_TOKENS
    topic_tokens = (
        query_strong
        - MEMORY_META_INTENT_TOKENS
        - MEMORY_META_ACTION_TOKENS
        - {
            "memory",
            "provider",
            "record",
            "prefetch",
            "continuity",
            "issue",
            "link",
            "remaining",
        }
    )
    if topic_tokens:
        return topic_tokens
    return expanded_tokens - WEAK_ANCHOR_TOKENS


def _is_preference_query(tokens: set[str], *, personal_query: bool) -> bool:
    return personal_query and bool(tokens & PREFERENCE_QUERY_TOKENS)


def _restore_preference_candidates(
    selected: list[CandidateScore], rejected: list[CandidateScore], tokens: set[str]
) -> None:
    """Let explicit personal-preference memories survive weak direct reranking.

    Rerankers often score short preference mirrors poorly because they do not
    directly answer the surface question.  For first-person preference-intent
    queries, a personal preference record with non-generic lexical/tag overlap is
    safer than letting an unrelated project record enter through the graph.
    """
    strong_tokens = tokens - WEAK_ANCHOR_TOKENS
    for candidate in list(rejected):
        if candidate.rejected_reason != "below_min_reranker_score":
            continue
        if candidate.record.kind not in PERSONAL_KINDS:
            continue
        record_tokens = _record_anchor_tokens(candidate.record)
        record_facets = _facets_for_record(candidate.record)
        if "personal_preference" not in record_facets:
            continue
        if not (
            strong_tokens & record_tokens
            or tokens & {_normalize_token(tag) for tag in candidate.record.tags}
        ):
            continue
        rejected.remove(candidate)
        candidate.rejected_reason = None
        candidate.retrieval_role = "direct_seed"
        candidate.reasons.append("preference_query")
        selected.append(candidate)


def _facets_for_tokens(tokens: set[str]) -> set[str]:
    return {facet for facet, facet_tokens in FACET_TOKEN_MAP.items() if tokens & facet_tokens}


def _facets_for_record(record: ContextRecord) -> set[str]:
    tokens = _record_anchor_tokens(record)
    facets = _facets_for_tokens(tokens)
    if record.scope_project and record.scope_project not in GENERIC_PROJECT_SCOPES:
        facets |= _facets_for_tokens(_query_tokens(record.scope_project))
    if record.kind == "active_project_state":
        facets.add("software_project")
    return facets


def _facets_incompatible(query_facets: set[str], record_facets: set[str]) -> bool:
    if not query_facets or not record_facets:
        return False
    if query_facets & record_facets:
        return False
    return any(pair <= (query_facets | record_facets) for pair in INCOMPATIBLE_FACET_PAIRS)


def _memory_system_record_without_meta_query(
    record: ContextRecord, query_facets: set[str], record_facets: set[str]
) -> bool:
    if "memory_system" in query_facets or "memory_system" not in record_facets:
        return False
    record_tags = {_normalize_token(tag) for tag in record.tags}
    return record.scope_project == "hermes-continuity-memory" or bool(
        record_tags & MEMORY_META_RECORD_ANCHORS
    )


def _apply_metadata_score(candidate: CandidateScore, tokens: set[str]) -> None:
    record = candidate.record
    record_tags = {_normalize_token(tag) for tag in record.tags}
    record_entities = {_normalize_token(entity) for entity in record.entities}
    record_text_tokens = _record_text_tokens(record)

    tag_matches = tokens & record_tags
    if tag_matches:
        candidate.tag_score += TAG_BONUS * len(tag_matches)
        candidate.reasons.append("tag")

    entity_matches = tokens & record_entities
    if entity_matches:
        candidate.entity_score += ENTITY_BONUS * len(entity_matches)
        candidate.reasons.append("entity")

    text_matches = tokens & record_text_tokens
    if text_matches:
        candidate.text_score += TEXT_MATCH_BONUS * len(text_matches)
        candidate.reasons.append("text")


def _apply_exact_identifier_score(candidate: CandidateScore, raw_tokens: set[str]) -> None:
    """Boost exact command/path/API-style identifiers even in high-collision corpora."""

    identifiers = _exact_identifier_tokens(raw_tokens)
    if not identifiers:
        return
    record = candidate.record
    context = context_from_record(record)
    context_values = {_normalize_token(value) for value in context.labels.values()}
    exact_context = identifiers & context_values
    identifier_like = {token for token in identifiers if _is_identifier_like_token(token)}
    exact_metadata = exact_context | (identifier_like & _record_identifier_tokens(record))
    if not exact_metadata:
        return
    candidate.entity_score += ENTITY_BONUS * len(exact_metadata)
    candidate.metadata_boost += 1.0
    if "exact_identifier" not in candidate.reasons:
        candidate.reasons.append("exact_identifier")
    if exact_context and "exact_context_identifier" not in candidate.reasons:
        candidate.reasons.append("exact_context_identifier")


def _exact_context_partition_bypass_record_ids(
    records: list[ContextRecord], raw_tokens: set[str], *, include_stale: bool
) -> set[str]:
    """Return records whose exact context identifier safely implies the partition.

    A literal command token like ``ldapd`` can safely imply ``os=openbsd`` when all
    matching context-labeled records share the same partition values.  Ambiguous
    tokens like ``ifconfig`` spanning OpenBSD and Linux must still require an
    explicit partition.
    """

    identifiers = _exact_identifier_tokens(raw_tokens)
    if not identifiers:
        return set()
    partition_signatures_by_token: dict[str, set[tuple[tuple[str, str], ...]]] = {}
    matching_record_ids_by_token: dict[str, set[str]] = {}
    for record in records:
        if not include_stale and _is_inactive_or_expired(record):
            continue
        context = context_from_record(record)
        if not context.labels:
            continue
        matched_tokens = identifiers & {
            _normalize_token(value) for value in context.labels.values()
        }
        if not matched_tokens:
            continue
        signature = tuple(
            sorted(
                (key, context.labels[key])
                for key in context.partition_keys
                if key in context.labels
            )
        )
        for token in matched_tokens:
            partition_signatures_by_token.setdefault(token, set()).add(signature)
            matching_record_ids_by_token.setdefault(token, set()).add(record.id)
    allowed: set[str] = set()
    for token, signatures in partition_signatures_by_token.items():
        if len(signatures) == 1:
            allowed.update(matching_record_ids_by_token.get(token, set()))
    return allowed


def _has_exact_identifier_match(candidate: CandidateScore) -> bool:
    return "exact_identifier" in candidate.reasons


def _exact_identifier_tokens(raw_tokens: set[str]) -> set[str]:
    return {
        token
        for token in raw_tokens
        if token
        and token not in WEAK_ANCHOR_TOKENS
        and token not in MEMORY_META_INTENT_TOKENS
        and len(token) >= 2
    }


def _is_identifier_like_token(token: str) -> bool:
    return any(char in token for char in (".", "_", "-", ":", "/")) or any(
        char.isdigit() for char in token
    )


def _record_identifier_tokens(record: ContextRecord) -> set[str]:
    tokens: set[str] = set()
    for value in [record.title, *record.tags, *record.entities]:
        normalized = _normalize_token(value)
        if normalized:
            tokens.add(normalized)
        tokens.update(_query_tokens(value))
    for source in record.sources:
        if source.uri:
            tokens.update(_query_tokens(source.uri))
    return tokens


def _is_weak_vector_only_candidate(
    candidate: CandidateScore, gate_config: RetrievalGateConfig
) -> bool:
    """Return true when semantic recall has no non-vector evidence.

    Neural/vector similarity is useful for paraphrases, but low-to-medium
    vector-only hits are the main source of noisy continuity injection.  Keep
    strong vector-only matches; reject weak ones unless FTS, tag, entity, or
    text scoring anchored the record to the query.
    """
    has_anchor = any(
        score > 0
        for score in (
            candidate.fts_score,
            candidate.tag_score,
            candidate.entity_score,
            candidate.text_score,
        )
    )
    return not has_anchor and 0 < candidate.vector_score < gate_config.min_vector_only_relevance


def _apply_scope_score(
    candidate: CandidateScore,
    tokens: set[str],
    scope_project: str | None,
) -> None:
    record = candidate.record
    if not scope_project or not record.scope_project:
        return
    if record.scope_project in GENERIC_PROJECT_SCOPES:
        return
    if record.scope_project != scope_project:
        if _scope_bonus_allowed(record, tokens):
            if record.kind == "active_project_state":
                candidate.scope_score += CAPSULE_SCOPE_BONUS
                candidate.reasons.append("project_capsule")
            return
        candidate.scope_score -= SCOPE_BONUS
        candidate.reasons.append("scope_mismatch")
        return
    if not _scope_bonus_allowed(record, tokens):
        return
    candidate.scope_score += SCOPE_BONUS
    candidate.reasons.append("scope")
    if record.kind == "active_project_state":
        candidate.scope_score += CAPSULE_SCOPE_BONUS
        candidate.reasons.append("project_capsule")


def _apply_boosts_and_penalties(candidate: CandidateScore, *, personal_query: bool) -> None:
    record = candidate.record
    candidate.metadata_boost += record.confidence * CONFIDENCE_WEIGHT
    candidate.metadata_boost += record.importance * IMPORTANCE_WEIGHT
    if personal_query and record.kind in PERSONAL_KINDS:
        candidate.metadata_boost += 0.75
        candidate.reasons.append("personal_query")
    candidate.penalties += TRUST_PENALTIES.get(record.trust_level, 0.0)


def _scope_bonus_allowed(record: ContextRecord, tokens: set[str]) -> bool:
    project_tokens = _query_tokens(record.scope_project or "")
    entity_tokens = {_normalize_token(entity) for entity in record.entities}
    tag_tokens = {_normalize_token(tag) for tag in record.tags}
    return bool(tokens & (project_tokens | entity_tokens | tag_tokens))


def _is_memory_meta_query(tokens: set[str]) -> bool:
    if tokens & MEMORY_META_INTENT_TOKENS:
        return True
    return bool((tokens & MEMORY_META_GENERIC_TOKENS) and (tokens & MEMORY_META_ACTION_TOKENS))


def _is_retrieval_helpfulness_meta_query(raw_tokens: set[str]) -> bool:
    return bool(
        raw_tokens & MEMORY_META_INTENT_TOKENS
        and raw_tokens & RETRIEVAL_HELPFULNESS_TOKENS
        and raw_tokens & RETRIEVAL_HELPFULNESS_CONTEXT_TOKENS
    )


def _memory_meta_record_allowed(
    record: ContextRecord, tokens: set[str], scope_project: str | None
) -> bool:
    if record.scope_project == "hermes-continuity-memory":
        return True
    if scope_project == "hermes-continuity-memory" and record.scope_project == scope_project:
        return True
    record_tags = {_normalize_token(tag) for tag in record.tags}
    record_entities = {_normalize_token(entity) for entity in record.entities}
    domain_tokens = record_tags | record_entities | _record_text_tokens(record)
    if domain_tokens & MEMORY_META_RECORD_ANCHORS:
        return True
    # Generic mirrored user/global memories should not ride along on meta-memory
    # queries merely because their display title contains "memory".
    if record.trust_level == "built_in_memory_mirror":
        return False
    return bool(tokens & (record_tags | record_entities))


def _record_text_tokens(record: ContextRecord) -> set[str]:
    title = "" if _is_boilerplate_mirror_title(record) else record.title
    return _query_tokens(f"{title} {record.summary} {record.details or ''}")


def _is_boilerplate_mirror_title(record: ContextRecord) -> bool:
    return (
        record.trust_level == "built_in_memory_mirror"
        and record.title.strip().lower() in BOILERPLATE_MIRROR_TITLES
    )


def _suppress_duplicate_families(
    candidates: list[CandidateScore],
) -> list[CandidateScore]:
    seen: set[str] = set()
    output: list[CandidateScore] = []
    for candidate in candidates:
        key = _record_family_key(candidate.record)
        if key in seen:
            continue
        seen.add(key)
        output.append(candidate)
    return output


def _record_family_key(record: ContextRecord) -> str:
    if record.trust_level == "corpus_distilled" and record.quality.get("context"):
        context = context_from_record(record)
        labels = ",".join(f"{key}={value}" for key, value in sorted(context.labels.items()))
        return f"{record.kind}:{record.title.lower()}:{labels}"
    if record.trust_level != "built_in_memory_mirror":
        return record.id
    tokens = sorted(_query_tokens(record.summary))
    return f"{record.kind}:{' '.join(tokens[:16])}"


def _is_inactive_or_expired(record: ContextRecord) -> bool:
    if record.status != "active":
        return True
    if not record.expires_at:
        return False
    expires_at = _parse_timestamp(record.expires_at)
    return expires_at is not None and expires_at <= datetime.now(UTC)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _raw_query_tokens(query: str) -> set[str]:
    return {_normalize_token(raw) for raw in re.findall(r"[\w:-]+", query.lower())}


def _query_tokens(query: str) -> set[str]:
    return {
        token
        for token in (_normalize_token(raw) for raw in re.findall(r"[\w:-]+", query.lower()))
        if token and token not in STOPWORDS
    }


def _expand_tokens(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    for token in list(tokens):
        expanded.update(ALIASES.get(token, set()))
        singular = _singularize(token)
        if singular != token:
            expanded.add(singular)
            expanded.update(ALIASES.get(singular, set()))
    if "timed" in tokens and "out" in tokens:
        expanded.add("timeout")
    if tokens & {"association", "association-graph", "graph"}:
        expanded.discard("work")
    return {_normalize_token(token) for token in expanded if token and token not in STOPWORDS}


def _normalize_token(token: str) -> str:
    token = token.lower().strip()
    return _singularize(token)


def _singularize(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def candidate_to_debug_dict(candidate: CandidateScore) -> dict[str, object]:
    """Serialize a candidate score for debug tooling."""

    payload = {
        "id": candidate.record.id,
        "kind": candidate.record.kind,
        "title": candidate.record.title,
        "summary": candidate.record.summary,
        "score": candidate.total,
        "base_relevance": candidate.base_relevance,
        "fts_score": candidate.fts_score,
        "vector_score": candidate.vector_score,
        "tag_score": candidate.tag_score,
        "entity_score": candidate.entity_score,
        "text_score": candidate.text_score,
        "scope_score": candidate.scope_score,
        "metadata_boost": candidate.metadata_boost,
        "reranker_score": candidate.reranker_score,
        "reranker_boost": candidate.reranker_boost,
        "association_score": candidate.association_score,
        "activation": candidate.activation,
        "retrieval_role": candidate.retrieval_role,
        "activation_trace": candidate.activation_trace,
        "penalties": candidate.penalties,
        "reasons": list(dict.fromkeys(candidate.reasons)),
        "rejected_reason": candidate.rejected_reason,
    }
    advice = tuning_advice_for_reason(candidate.rejected_reason)
    if advice is not None:
        payload["tuning_advice"] = advice
    return payload


def tuning_advice_for_reason(reason: str | None) -> dict[str, str] | None:
    """Return plain-English tuning advice for a debug rejection/cut reason."""
    if not reason:
        return None
    advice_by_reason = {
        "below_min_base_relevance": {
            "reason": reason,
            "config": "retrieval_gates.min_base_relevance",
            "try": "If this record should match, lower this threshold slightly or add stronger tags/entities. If weak one-word matches are noisy, raise it.",
        },
        "weak_vector_only_without_anchor": {
            "reason": reason,
            "config": "retrieval_gates.min_vector_only_relevance or retrieval_gates.weak_vector_only",
            "try": "If vector-only paraphrases are useful, lower min_vector_only_relevance slightly. If vector noise is the problem, raise it or keep weak_vector_only enabled.",
        },
        "facet_incompatible_candidate": {
            "reason": reason,
            "config": "retrieval_gates.facet_compatibility",
            "try": "If this is truly relevant, improve record tags/entities or temporarily disable this gate to confirm. Keep it enabled for polysemous terms like software Framework vs hardware Framework.",
        },
        "facet_incompatible_activation_seed": {
            "reason": reason,
            "config": "retrieval_gates.facet_compatibility",
            "try": "If graph rescue should cross this domain boundary, improve tags/entities or test with facet_compatibility disabled. Keep enabled when unrelated domains bleed together.",
        },
        "memory_system_record_without_meta_query": {
            "reason": reason,
            "config": "retrieval_gates.memory_meta",
            "try": "If this was meant to ask about continuity/memory, use explicit terms like continuity, retrieval, or memory provider. Disable only for diagnostics.",
        },
        "memory_system_neighbor_without_meta_query": {
            "reason": reason,
            "config": "retrieval_gates.memory_meta",
            "try": "If graph neighbors from memory-system records are desired, make the query explicitly memory-related. Keep this enabled to avoid implementation-status noise.",
        },
        "low_information_direct_query": {
            "reason": reason,
            "config": "retrieval_gates.low_information",
            "try": "Add a durable project/entity word to the query. Disable only if short local commands are intentionally meaningful in your workflow.",
        },
        "low_information_query_activation_seed": {
            "reason": reason,
            "config": "retrieval_gates.low_information",
            "try": "Add a concrete anchor before relying on association graph rescue. Keep enabled if vague follow-ups pull stale context.",
        },
        "weak_project_status_candidate": {
            "reason": reason,
            "config": "retrieval_gates.project_status_anchor",
            "try": "Add project-specific tags/entities or mention the project in the query. Disable only for trusted, scoped deployments.",
        },
        "personal_project_candidate_mismatch": {
            "reason": reason,
            "config": "retrieval_gates.personal_project",
            "try": "Add the relevant project/entity name if a personal query should retrieve project state. Keep enabled if preferences pull roadmap noise.",
        },
        "weak_anchor_activation_seed": {
            "reason": reason,
            "config": "retrieval_gates.activation_anchor",
            "try": "Improve tags/entities on the seed record first. Disable only when testing graph rescue on a clean corpus.",
        },
        "below_min_reranker_score": {
            "reason": reason,
            "config": "reranker.min_score or retrieval_gates.strong_personal_anchor_reranker_bypass",
            "try": "Lower reranker.min_score if the reranker is too strict. For strongly tagged personal facts, keep the personal-anchor bypass enabled.",
        },
        "below_activation_threshold": {
            "reason": reason,
            "config": "association_graph.activation_threshold or association_graph.hop_decay",
            "try": "Lower activation_threshold or raise hop_decay if graph rescue is too quiet. Raise them if graph traversal fans out too broadly.",
        },
    }
    return advice_by_reason.get(reason)
