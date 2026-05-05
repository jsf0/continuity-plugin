from __future__ import annotations

from pathlib import Path

from continuity.ingest.models import SourceDocument
from continuity.ingest.parsers import MarkdownParser, TextParser
from continuity.ingest.segmenters import FixedWindowSegmenter, HeadingSectionSegmenter

FIXTURE_ROOT = Path("tests/fixtures/ingestion/simple_docs")


def _document(relative_path: str, source_type: str) -> SourceDocument:
    path = FIXTURE_ROOT / relative_path
    return SourceDocument(
        source_id=f"file://{relative_path}",
        source_type=source_type,
        uri=f"file://{relative_path}",
        title=path.name,
        metadata={"path": str(path), "relative_path": relative_path},
        scope_project="continuity-ingestion-fixture",
        scope_repo=str(FIXTURE_ROOT),
    )


def test_heading_section_segmenter_groups_markdown_under_headings_with_source_locations() -> None:
    document = _document("docs/architecture.md", "markdown")
    parsed = MarkdownParser().parse(document)

    segments = list(HeadingSectionSegmenter().segment(parsed, document))

    assert [segment.title for segment in segments] == [
        "Architecture",
        "Retrieval model",
        "Source references",
    ]
    assert [segment.kind for segment in segments] == ["section", "section", "section"]
    assert "retrieves compact records" in segments[1].text
    assert segments[1].segment_id == "file://docs/architecture.md#retrieval-model"
    assert segments[1].source_id == document.source_id
    assert segments[1].location is not None
    assert segments[1].location.line_start == 3
    assert segments[1].location.line_end == 6
    assert segments[1].metadata["heading_path"] == ["Architecture", "Retrieval model"]
    assert len(str(segments[1].metadata["content_hash"])) == 64
    assert segments[1].scope_project == "continuity-ingestion-fixture"


def test_heading_section_segmenter_falls_back_to_whole_document_without_headings() -> None:
    path = FIXTURE_ROOT / "plain.txt"
    path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    document = _document("plain.txt", "text")
    parsed = TextParser().parse(document)

    segments = list(HeadingSectionSegmenter().segment(parsed, document))

    assert len(segments) == 1
    assert segments[0].kind == "document"
    assert segments[0].title == "plain.txt"
    assert segments[0].text == "alpha\nbeta\ngamma"
    assert segments[0].location is not None
    assert segments[0].location.line_start == 1
    assert segments[0].location.line_end == 3


def test_fixed_window_segmenter_splits_blocks_into_line_bounded_windows() -> None:
    path = FIXTURE_ROOT / "window.txt"
    path.write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
    document = _document("window.txt", "text")
    parsed = TextParser().parse(document)

    segments = list(FixedWindowSegmenter(max_lines=2).segment(parsed, document))

    assert [segment.text for segment in segments] == ["one\ntwo", "three\nfour", "five"]
    assert [segment.segment_id for segment in segments] == [
        "file://window.txt#lines-1-2",
        "file://window.txt#lines-3-4",
        "file://window.txt#lines-5-5",
    ]
    assert segments[0].location is not None
    assert segments[0].location.line_start == 1
    assert segments[0].location.line_end == 2
    assert segments[2].location is not None
    assert segments[2].location.line_start == 5
    assert segments[2].location.line_end == 5
