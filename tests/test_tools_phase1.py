from __future__ import annotations

from continuity import CONTINUITY_STATUS_SCHEMA, ContinuityProvider


def test_status_tool_schema_is_openai_function_shape() -> None:
    schema = CONTINUITY_STATUS_SCHEMA

    assert schema["name"] == "continuity_status"
    assert isinstance(schema["description"], str)
    assert schema["parameters"]["type"] == "object"
    assert schema["parameters"]["required"] == []


def test_provider_exposes_only_status_tool_in_phase1() -> None:
    provider = ContinuityProvider()

    schemas = provider.get_tool_schemas()

    assert schemas == [CONTINUITY_STATUS_SCHEMA]
