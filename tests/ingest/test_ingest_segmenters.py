from __future__ import annotations

from pathlib import Path

from continuity.ingest.models import SourceDocument
from continuity.ingest.parsers import ManPageParser, MarkdownParser, TextParser
from continuity.ingest.segmenters import (
    FixedWindowSegmenter,
    HeadingSectionSegmenter,
    ManPageSectionSegmenter,
)

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


def test_heading_section_segmenter_falls_back_to_whole_document_without_headings(tmp_path) -> None:
    path = tmp_path / "plain.txt"
    path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    document = SourceDocument(
        source_id="file://plain.txt",
        source_type="text",
        uri="file://plain.txt",
        title="plain.txt",
        metadata={"path": str(path), "relative_path": "plain.txt"},
    )
    parsed = TextParser().parse(document)

    segments = list(HeadingSectionSegmenter().segment(parsed, document))

    assert len(segments) == 1
    assert segments[0].kind == "document"
    assert segments[0].title == "plain.txt"
    assert segments[0].text == "alpha\nbeta\ngamma"
    assert segments[0].location is not None
    assert segments[0].location.line_start == 1
    assert segments[0].location.line_end == 3


def test_man_page_section_segmenter_groups_operational_sections(tmp_path) -> None:
    path = tmp_path / "rcctl.8.txt"
    path.write_text(
        "RCCTL(8) OpenBSD System Manager's Manual\n"
        "NAME\n"
        "rcctl - control OpenBSD daemons\n"
        "SYNOPSIS\n"
        "rcctl enable daemon\n"
        "rcctl start daemon\n"
        "DESCRIPTION\n"
        "The rcctl utility controls OpenBSD services.\n"
        "FILES\n"
        "/etc/rc.conf.local stores local daemon configuration.\n",
        encoding="utf-8",
    )
    document = SourceDocument(
        source_id="file://rcctl.8.txt",
        source_type="text",
        uri="file://rcctl.8.txt",
        title="rcctl.8.txt",
        metadata={"path": str(path), "relative_path": "rcctl.8.txt"},
    )
    parsed = ManPageParser().parse(document)

    segments = ManPageSectionSegmenter().segment(parsed, document)

    assert [segment.title for segment in segments] == [
        "NAME",
        "SYNOPSIS",
        "DESCRIPTION",
        "FILES",
    ]
    synopsis = segments[1]
    assert synopsis.kind == "manpage_section"
    assert synopsis.metadata["manpage_section"] == "SYNOPSIS"
    assert synopsis.metadata["manpage_name"] == "rcctl"
    assert synopsis.segment_id == "file://rcctl.8.txt#synopsis"
    assert "rcctl enable daemon" in synopsis.text


def test_heading_section_segmenter_marks_example_code_and_table_sections(tmp_path) -> None:
    path = tmp_path / "memory.md"
    path.write_text(
        "# Memory\n"
        "## Example memory entries\n"
        "| Name | Value |\n"
        "| --- | --- |\n"
        "| Project | demo |\n"
        "```yaml\n"
        "user: fake\n"
        "```\n",
        encoding="utf-8",
    )
    document = SourceDocument(
        source_id="file://memory.md",
        source_type="markdown",
        uri="file://memory.md",
        title="memory.md",
        metadata={"path": str(path), "relative_path": "memory.md"},
    )
    parsed = MarkdownParser().parse(document)

    segments = HeadingSectionSegmenter().segment(parsed, document)

    example_segment = segments[1]
    assert example_segment.metadata["contains_example"] is True
    assert example_segment.metadata["contains_code_block"] is True
    assert example_segment.metadata["contains_table"] is True


def test_fixed_window_segmenter_splits_blocks_into_line_bounded_windows(tmp_path) -> None:
    path = tmp_path / "window.txt"
    path.write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
    document = SourceDocument(
        source_id="file://window.txt",
        source_type="text",
        uri="file://window.txt",
        title="window.txt",
        metadata={"path": str(path), "relative_path": "window.txt"},
    )
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
