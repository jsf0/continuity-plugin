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
