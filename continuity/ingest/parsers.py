"""Document parsers for corpus ingestion."""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from continuity.ingest.models import ParsedBlock, ParsedDocument, SourceDocument, SourceLocation

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+?)\s*$")
_FENCE_RE = re.compile(r"^```\s*([A-Za-z0-9_+.-]*)\s*$")
_MANPAGE_SECTION_NAMES = {
    "NAME",
    "SYNOPSIS",
    "DESCRIPTION",
    "OPTIONS",
    "FILES",
    "EXAMPLES",
    "EXIT STATUS",
    "SEE ALSO",
    "STANDARDS",
    "HISTORY",
    "AUTHORS",
    "CAVEATS",
    "BUGS",
}


class MarkdownParser:
    """Simple line-oriented Markdown parser preserving useful source locations."""

    name = "markdown"
    supported_types: ClassVar[list[str]] = ["markdown", "rst"]

    def parse(self, document: SourceDocument) -> ParsedDocument:
        path = _path_from_document(document)
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        blocks: list[ParsedBlock] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            line_number = index + 1
            fence_match = _FENCE_RE.match(line)
            if fence_match:
                language = fence_match.group(1) or None
                code_lines: list[str] = []
                start_line = line_number
                index += 1
                while index < len(lines):
                    if _FENCE_RE.match(lines[index]):
                        break
                    code_lines.append(lines[index])
                    index += 1
                end_line = index + 1 if index < len(lines) else len(lines)
                blocks.append(
                    ParsedBlock(
                        block_id=f"{document.source_id}:line-{start_line}",
                        kind="code_block",
                        text="\n".join(code_lines),
                        location=_location(document, start_line, end_line),
                        metadata={"language": language},
                    )
                )
                index += 1
                continue

            heading_match = _HEADING_RE.match(line)
            if heading_match:
                blocks.append(
                    ParsedBlock(
                        block_id=f"{document.source_id}:line-{line_number}",
                        kind="heading",
                        text=heading_match.group(2).strip(),
                        level=len(heading_match.group(1)),
                        location=_location(document, line_number, line_number),
                    )
                )
            elif not line.strip():
                blocks.append(
                    ParsedBlock(
                        block_id=f"{document.source_id}:line-{line_number}",
                        kind="blank",
                        text="",
                        location=_location(document, line_number, line_number),
                    )
                )
            elif list_match := _LIST_ITEM_RE.match(line):
                blocks.append(
                    ParsedBlock(
                        block_id=f"{document.source_id}:line-{line_number}",
                        kind="list_item",
                        text=list_match.group(1).strip(),
                        location=_location(document, line_number, line_number),
                    )
                )
            else:
                blocks.append(
                    ParsedBlock(
                        block_id=f"{document.source_id}:line-{line_number}",
                        kind="paragraph",
                        text=line.strip(),
                        location=_location(document, line_number, line_number),
                    )
                )
            index += 1

        return ParsedDocument(
            source_id=document.source_id,
            source_type=document.source_type,
            title=document.title,
            text=text,
            blocks=blocks,
            metadata={"parser": self.name},
        )


class TextParser:
    """Plaintext parser that preserves one parsed block per line."""

    name = "text"
    supported_types: ClassVar[list[str]] = ["text", "binary"]

    def parse(self, document: SourceDocument) -> ParsedDocument:
        path = _path_from_document(document)
        text = path.read_text(encoding="utf-8")
        blocks = [
            ParsedBlock(
                block_id=f"{document.source_id}:line-{line_number}",
                kind="blank" if not line.strip() else "line",
                text=line.strip(),
                location=_location(document, line_number, line_number),
            )
            for line_number, line in enumerate(text.splitlines(), start=1)
        ]
        return ParsedDocument(
            source_id=document.source_id,
            source_type=document.source_type,
            title=document.title,
            text=text,
            blocks=blocks,
            metadata={"parser": self.name},
        )


class ManPageParser:
    """Line-oriented parser for rendered Unix manual pages."""

    name = "manpage"
    supported_types: ClassVar[list[str]] = ["text"]

    def parse(self, document: SourceDocument) -> ParsedDocument:
        path = _path_from_document(document)
        text = path.read_text(encoding="utf-8")
        blocks: list[ParsedBlock] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = _clean_manpage_line(line)
            if not stripped or _is_manpage_noise(stripped, document):
                kind = "blank"
                level = None
                metadata = {}
            elif _is_manpage_heading(stripped):
                kind = "heading"
                level = 1
                metadata = {"manpage_section": stripped}
            else:
                kind = "line"
                level = None
                metadata = {}
            blocks.append(
                ParsedBlock(
                    block_id=f"{document.source_id}:line-{line_number}",
                    kind=kind,
                    text=stripped,
                    level=level,
                    location=_location(document, line_number, line_number),
                    metadata=metadata,
                )
            )
        return ParsedDocument(
            source_id=document.source_id,
            source_type=document.source_type,
            title=document.title,
            text=text,
            blocks=blocks,
            metadata={"parser": self.name},
        )


def parser_for_document(
    document: SourceDocument, *, recipe: str | None = None
) -> MarkdownParser | TextParser | ManPageParser:
    """Return the default parser for a source document."""

    if recipe in {"manpage", "openbsd-manpages"}:
        return ManPageParser()
    if document.source_type in {"markdown", "rst"}:
        return MarkdownParser()
    return TextParser()


def _is_manpage_heading(line: str) -> bool:
    return line in _MANPAGE_SECTION_NAMES


def _clean_manpage_line(line: str) -> str:
    text = re.sub(r"(?:0|1|22|24|4)m", "", line)
    text = text.replace("\u2010", "-")
    return re.sub(r"[ \t]+", " ", text).strip()


def _is_manpage_noise(line: str, document: SourceDocument) -> bool:
    title = (document.title or "").split(".", 1)[0].upper()
    return line.startswith("Debian ") or (bool(title) and title in line and "Manual" in line)


def _path_from_document(document: SourceDocument) -> Path:
    path = document.metadata.get("path")
    if not path:
        raise ValueError("document metadata must include path")
    return Path(str(path))


def _location(document: SourceDocument, line_start: int, line_end: int) -> SourceLocation:
    return SourceLocation(
        uri=document.uri,
        path=str(document.metadata.get("path")) if document.metadata.get("path") else None,
        line_start=line_start,
        line_end=line_end,
    )
