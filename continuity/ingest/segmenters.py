"""Segmenters for parsed corpus documents."""

from __future__ import annotations

import re

from continuity.ingest.models import (
    ParsedBlock,
    ParsedDocument,
    SourceDocument,
    SourceLocation,
    SourceSegment,
    stable_hash,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class HeadingSectionSegmenter:
    """Group parsed Markdown-like blocks into heading sections."""

    name = "heading-section"

    def segment(self, parsed: ParsedDocument, document: SourceDocument) -> list[SourceSegment]:
        heading_indexes = [
            index for index, block in enumerate(parsed.blocks) if block.kind == "heading"
        ]
        if not heading_indexes:
            return [_whole_document_segment(parsed, document)] if parsed.blocks else []

        segments: list[SourceSegment] = []
        heading_stack: list[ParsedBlock] = []
        for position, block_index in enumerate(heading_indexes):
            heading = parsed.blocks[block_index]
            while heading_stack and (heading_stack[-1].level or 1) >= (heading.level or 1):
                heading_stack.pop()
            heading_stack.append(heading)
            next_heading_index = (
                heading_indexes[position + 1]
                if position + 1 < len(heading_indexes)
                else len(parsed.blocks)
            )
            section_blocks = parsed.blocks[block_index:next_heading_index]
            segment_text = _blocks_to_text(section_blocks)
            location = _combined_location(section_blocks, document)
            heading_path = [item.text for item in heading_stack]
            segments.append(
                SourceSegment(
                    segment_id=f"{document.source_id}#{_slugify(heading.text)}",
                    source_id=document.source_id,
                    kind="section",
                    title=heading.text,
                    text=segment_text,
                    location=location,
                    metadata={
                        "heading_path": heading_path,
                        "content_hash": stable_hash(segment_text),
                    },
                    scope_project=document.scope_project,
                    scope_repo=document.scope_repo,
                    scope_user=document.scope_user,
                    scope_profile=document.scope_profile,
                )
            )
        return segments


class FixedWindowSegmenter:
    """Split parsed blocks into fixed line-count windows."""

    name = "fixed-window"

    def __init__(self, *, max_lines: int = 80) -> None:
        if max_lines < 1:
            raise ValueError("max_lines must be positive")
        self.max_lines = max_lines

    def segment(self, parsed: ParsedDocument, document: SourceDocument) -> list[SourceSegment]:
        content_blocks = [block for block in parsed.blocks if block.kind != "blank"]
        if not content_blocks:
            return []
        segments: list[SourceSegment] = []
        for index in range(0, len(content_blocks), self.max_lines):
            window_blocks = content_blocks[index : index + self.max_lines]
            location = _combined_location(window_blocks, document)
            line_start = (
                location.line_start if location and location.line_start is not None else index + 1
            )
            line_end = (
                location.line_end if location and location.line_end is not None else line_start
            )
            text = _blocks_to_text(window_blocks)
            segments.append(
                SourceSegment(
                    segment_id=f"{document.source_id}#lines-{line_start}-{line_end}",
                    source_id=document.source_id,
                    kind="window",
                    title=f"{document.title or document.source_id} lines {line_start}-{line_end}",
                    text=text,
                    location=location,
                    metadata={"content_hash": stable_hash(text)},
                    scope_project=document.scope_project,
                    scope_repo=document.scope_repo,
                    scope_user=document.scope_user,
                    scope_profile=document.scope_profile,
                )
            )
        return segments


def _whole_document_segment(parsed: ParsedDocument, document: SourceDocument) -> SourceSegment:
    content_blocks = [block for block in parsed.blocks if block.kind != "blank"]
    text = _blocks_to_text(content_blocks)
    return SourceSegment(
        segment_id=f"{document.source_id}#document",
        source_id=document.source_id,
        kind="document",
        title=document.title,
        text=text,
        location=_combined_location(content_blocks, document),
        metadata={"content_hash": stable_hash(text)},
        scope_project=document.scope_project,
        scope_repo=document.scope_repo,
        scope_user=document.scope_user,
        scope_profile=document.scope_profile,
    )


def _blocks_to_text(blocks: list[ParsedBlock]) -> str:
    return "\n".join(block.text for block in blocks if block.kind != "blank" and block.text).strip()


def _combined_location(
    blocks: list[ParsedBlock], document: SourceDocument
) -> SourceLocation | None:
    located = [block.location for block in blocks if block.location is not None]
    if not located:
        return None
    line_starts = [location.line_start for location in located if location.line_start is not None]
    line_ends = [location.line_end for location in located if location.line_end is not None]
    return SourceLocation(
        uri=document.uri,
        path=str(document.metadata.get("path")) if document.metadata.get("path") else None,
        line_start=min(line_starts) if line_starts else None,
        line_end=max(line_ends) if line_ends else None,
    )


def _slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug or "section"
