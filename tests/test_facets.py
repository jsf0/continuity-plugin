from __future__ import annotations

from continuity.facets import facets_for_record
from continuity.models import ContextRecord


def _record(**overrides) -> ContextRecord:
    values = {
        "id": "r_facets",
        "kind": "project_convention",
        "title": "FastAPI request routing",
        "summary": "The API framework routes JSON requests to handlers.",
        "tags": ["api", "software"],
        "entities": ["FastAPI"],
        "trust_level": "explicit_user",
    }
    values.update(overrides)
    return ContextRecord.new(**values)


def test_facets_for_software_project_record() -> None:
    assert "software_project" in facets_for_record(_record())


def test_facets_for_active_project_state_defaults_to_software_project() -> None:
    assert "software_project" in facets_for_record(_record(kind="active_project_state"))
