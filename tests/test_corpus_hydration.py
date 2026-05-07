from __future__ import annotations

import json
from pathlib import Path

from continuity import ContinuityProvider
from continuity.ingest.importer import ContinuityImporter, imported_record_id
from continuity.ingest.models import (
    CandidateRecord,
    SourceDocument,
    SourceLocation,
    SourceSegment,
)
from continuity.ingest.models import (
    SourceRef as IngestSourceRef,
)
from continuity.store import ContinuityStore


def test_import_stores_durable_corpus_segments_and_pointers(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    document = SourceDocument(
        source_id="doc_ldomctl_8",
        source_type="manpage",
        uri="file://usr.sbin/ldomctl/ldomctl.8",
        title="ldomctl(8)",
        collection="openbsd-manpages",
        scope_repo="/tmp/openbsd-src-sparse",
    )
    segment = SourceSegment(
        segment_id="seg_ldomctl_examples",
        source_id="doc_ldomctl_8",
        kind="section",
        title="EXAMPLES",
        text="EXAMPLES\n# ldomctl list\nfactory-default [current]\n",
        location=SourceLocation(
            uri="file://usr.sbin/ldomctl/ldomctl.8",
            line_start=79,
            line_end=82,
        ),
        scope_repo="/tmp/openbsd-src-sparse",
    )
    candidate = CandidateRecord(
        candidate_id="cand_ldomctl_examples",
        kind="codebase_fact",
        title="Manpage EXAMPLES: ldomctl",
        summary="EXAMPLES A system using factory defaults has factory-default.",
        scope_repo="/tmp/openbsd-src-sparse",
        tags=["manpage", "examples"],
        entities=["ldomctl"],
        confidence=0.82,
        importance=0.62,
        source_refs=[
            IngestSourceRef(
                type="file",
                uri="file://usr.sbin/ldomctl/ldomctl.8",
                segment_id="seg_ldomctl_examples",
                section="EXAMPLES",
                line_start=79,
                line_end=82,
            )
        ],
    )

    result = ContinuityImporter(store).import_records(
        [candidate], dry_run=False, documents=[document], segments=[segment]
    )

    assert result.failed == []
    record_id = imported_record_id(candidate)
    record = store.get_record(record_id)
    assert record is not None
    assert record.sources[0].type == "corpus_segment"
    assert record.sources[0].document_id == "doc_ldomctl_8"
    assert record.sources[0].segment_id == "seg_ldomctl_examples"
    assert record.sources[0].content_hash

    hydrated = store.hydrate_record_sources(record_id, max_chars=2000)
    assert hydrated[0]["segment_id"] == "seg_ldomctl_examples"
    assert hydrated[0]["text"] == segment.text
    assert hydrated[0]["truncated"] is False


def test_continuity_hydrate_tool_returns_full_cited_source_text(tmp_path: Path) -> None:
    provider = ContinuityProvider()
    provider.initialize(session_id="corpus-hydration", hermes_home=str(tmp_path))
    assert provider._store is not None
    store = provider._store

    document = SourceDocument(
        source_id="doc_ldom_conf_5",
        source_type="manpage",
        uri="file://usr.sbin/ldomctl/ldom.conf.5",
        title="ldom.conf(5)",
    )
    segment = SourceSegment(
        segment_id="seg_ldom_conf_domain",
        source_id="doc_ldom_conf_5",
        kind="section",
        title="DESCRIPTION",
        text='domain "puffy" {\n\tvcpu 12\n\tmemory 4G\n}\n',
    )
    candidate = CandidateRecord(
        candidate_id="cand_ldom_conf_domain",
        kind="codebase_fact",
        title="Manpage DESCRIPTION: ldom.conf",
        summary="ldom.conf defines domains with domain name braces.",
        source_refs=[
            IngestSourceRef(
                type="file",
                uri="file://usr.sbin/ldomctl/ldom.conf.5",
                segment_id="seg_ldom_conf_domain",
                section="DESCRIPTION",
            )
        ],
    )
    ContinuityImporter(store).import_records(
        [candidate], dry_run=False, documents=[document], segments=[segment]
    )
    record_id = imported_record_id(candidate)

    payload = json.loads(
        provider.handle_tool_call("continuity_hydrate", {"id": record_id, "max_chars": 2000})
    )

    assert payload["success"] is True
    assert payload["record"]["id"] == record_id
    assert payload["sources"][0]["text"] == segment.text
    assert "vcpu 12" in payload["sources"][0]["text"]
