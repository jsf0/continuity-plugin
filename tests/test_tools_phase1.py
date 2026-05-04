from __future__ import annotations

from continuity import CONTINUITY_STATUS_SCHEMA, ContinuityProvider


def test_status_tool_schema_is_openai_function_shape() -> None:
    schema = CONTINUITY_STATUS_SCHEMA

    assert schema["name"] == "continuity_status"
    assert isinstance(schema["description"], str)
    assert schema["parameters"]["type"] == "object"
    assert schema["parameters"]["required"] == []


def test_provider_exposes_phase4_tool_schemas() -> None:
    provider = ContinuityProvider()

    names = {schema["name"] for schema in provider.get_tool_schemas()}

    assert CONTINUITY_STATUS_SCHEMA in provider.get_tool_schemas()
    assert names == {
        "continuity_status",
        "continuity_search",
        "continuity_get",
        "continuity_add",
        "continuity_delete",
        "continuity_archive",
        "continuity_restore",
        "continuity_prune_stale",
        "continuity_debug_retrieval",
        "continuity_association_edges",
        "continuity_reindex_vectors",
    }
