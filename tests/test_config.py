from __future__ import annotations

from continuity.config import ContinuityConfig


def test_config_defaults_match_phase3_spec() -> None:
    config = ContinuityConfig.from_mapping({})

    assert config.max_records == 5
    assert config.max_chars == 1800
    assert config.min_score == 0.1
    assert config.include_sources is True
    assert config.include_scores is False
    assert config.session_strategy == "per-repo"
    assert config.vector_enabled is False


def test_config_clamps_unsafe_values() -> None:
    config = ContinuityConfig.from_mapping(
        {
            "max_records": 0,
            "max_chars": 20,
            "min_score": -1,
            "include_sources": False,
            "include_scores": True,
            "session_strategy": "unknown",
        }
    )

    assert config.max_records == 1
    assert config.max_chars == 200
    assert config.min_score == 0.0
    assert config.include_sources is False
    assert config.include_scores is True
    assert config.session_strategy == "per-repo"


def test_config_parses_sentence_transformers_vector_backend() -> None:
    config = ContinuityConfig.from_mapping(
        {
            "vector": {
                "enabled": True,
                "backend": "sentence-transformers",
                "embedding_model": "BAAI/bge-small-en-v1.5",
                "batch_size": 8,
                "normalize": False,
            },
            "pinned_system_prompt": {"enabled": True},
        }
    )

    assert config.vector_enabled is True
    assert config.vector_backend == "sentence-transformers"
    assert config.embedding_model == "BAAI/bge-small-en-v1.5"
    assert config.embedding_batch_size == 8
    assert config.embedding_normalize is False
    assert config.pinned_system_prompt.enabled is True


def test_config_parses_guidance_only_pinned_system_prompt() -> None:
    config = ContinuityConfig.from_mapping(
        {
            "pinned_system_prompt": {
                "enabled": True,
                "include_records": False,
                "max_records": 0,
            }
        }
    )

    assert config.pinned_system_prompt.enabled is True
    assert config.pinned_system_prompt.include_records is False
    assert config.pinned_system_prompt.max_records == 0


def test_config_parses_retrieval_gate_tunables() -> None:
    config = ContinuityConfig.from_mapping(
        {
            "retrieval_gates": {
                "min_base_relevance": 0.2,
                "min_vector_relevance": 0.04,
                "min_vector_only_relevance": 3.2,
                "weak_vector_only": False,
                "facet_compatibility": False,
                "memory_meta": False,
                "low_information": False,
                "project_status_anchor": False,
                "personal_project": False,
                "activation_anchor": False,
                "strong_personal_anchor_reranker_bypass": False,
            }
        }
    )

    assert config.retrieval_gates.min_base_relevance == 0.2
    assert config.retrieval_gates.min_vector_relevance == 0.04
    assert config.retrieval_gates.min_vector_only_relevance == 3.2
    assert config.retrieval_gates.weak_vector_only is False
    assert config.retrieval_gates.facet_compatibility is False
    assert config.retrieval_gates.memory_meta is False
    assert config.retrieval_gates.low_information is False
    assert config.retrieval_gates.project_status_anchor is False
    assert config.retrieval_gates.personal_project is False
    assert config.retrieval_gates.activation_anchor is False
    assert config.retrieval_gates.strong_personal_anchor_reranker_bypass is False
