from __future__ import annotations

from pathlib import Path

from continuity.ingest.models import SourceDocument
from continuity.ingest.parsers import MarkdownParser, TextParser, parser_for_document

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


def test_markdown_parser_emits_heading_paragraph_list_and_blank_blocks_with_locations() -> None:
    document = _document("docs/release.md", "markdown")

    parsed = MarkdownParser().parse(document)

    assert parsed.source_id == "file://docs/release.md"
    assert parsed.source_type == "markdown"
    assert parsed.title == "release.md"
    assert parsed.text and "Release checklist" in parsed.text
    assert parsed.metadata["parser"] == "markdown"
    kinds = [block.kind for block in parsed.blocks]
    assert kinds == [
        "heading",
        "blank",
        "heading",
        "blank",
        "list_item",
        "list_item",
        "list_item",
        "list_item",
        "list_item",
    ]
    first_heading = parsed.blocks[0]
    assert first_heading.text == "Release"
    assert first_heading.level == 1
    assert first_heading.location is not None
    assert first_heading.location.line_start == 1
    assert first_heading.location.path and first_heading.location.path.endswith("docs/release.md")
    checklist_heading = parsed.blocks[2]
    assert checklist_heading.text == "Release checklist"
    assert checklist_heading.level == 2
    assert checklist_heading.location is not None
    assert checklist_heading.location.line_start == 3


def test_markdown_parser_classifies_code_fence_blocks(tmp_path) -> None:
    path = tmp_path / "with_code.md"
    path.write_text("# With Code\n\n```bash\npytest tests/ -q\n```\n", encoding="utf-8")
    document = SourceDocument(
        source_id="file://with_code.md",
        source_type="markdown",
        uri="file://with_code.md",
        title="with_code.md",
        metadata={"path": str(path), "relative_path": "with_code.md"},
    )

    parsed = MarkdownParser().parse(document)

    code_blocks = [block for block in parsed.blocks if block.kind == "code_block"]
    assert len(code_blocks) == 1
    assert code_blocks[0].text == "pytest tests/ -q"
    assert code_blocks[0].metadata["language"] == "bash"
    assert code_blocks[0].location is not None
    assert code_blocks[0].location.line_start == 3
    assert code_blocks[0].location.line_end == 5


def test_text_parser_emits_line_and_blank_blocks() -> None:
    path = FIXTURE_ROOT / "notes.txt"
    path.write_text("First line\n\nSecond line\n", encoding="utf-8")
    document = _document("notes.txt", "text")

    parsed = TextParser().parse(document)

    assert parsed.source_type == "text"
    assert [block.kind for block in parsed.blocks] == ["line", "blank", "line"]
    assert parsed.blocks[0].text == "First line"
    assert parsed.blocks[2].location is not None
    assert parsed.blocks[2].location.line_start == 3


def test_parser_for_document_uses_source_type() -> None:
    assert isinstance(parser_for_document(_document("README.md", "markdown")), MarkdownParser)
    assert isinstance(parser_for_document(_document("notes.txt", "text")), TextParser)
