"""Generic metadata extraction for memory records.

This extractor intentionally avoids project/user-specific rules.  It extracts
literal evidence present in text and can match already-known corpus metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedMetadata:
    tags: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    extraction_notes: tuple[str, ...] = ()


def extract_metadata(
    text: str,
    *,
    known_entities: set[str] | None = None,
    known_tags: set[str] | None = None,
    max_entities: int = 12,
    max_tags: int = 12,
) -> ExtractedMetadata:
    """Extract conservative tags/entities from literal text.

    The function does not infer domain tags from private entities.  It only
    preserves explicit tag-like markers, capitalized/code-like phrases, and
    terms already present in the known corpus vocabulary.
    """

    entities: set[str] = set()
    tags: set[str] = set()
    notes: list[str] = []

    for tag in re.findall(r"(?:^|\s)(?:#|tag:)([A-Za-z0-9][\w:-]{1,60})", text):
        tags.add(_normalize_tag(tag))
    if tags:
        notes.append("explicit_tag_markers")

    for phrase in _capitalized_phrases(text):
        entities.add(phrase)
    if entities:
        notes.append("capitalized_phrase_entities")

    for token in re.findall(r"\b[a-z][a-z0-9]+(?:[-_.][a-z0-9]+)+\b", text):
        # Code/project identifiers are useful literal entities, but not broad tags.
        entities.add(token)
    if any(note != "literal_identifier_entities" for note in notes):
        notes.append("literal_identifier_entities")

    lower_text = text.lower()
    for entity in known_entities or set():
        if entity and entity.lower() in lower_text:
            entities.add(entity)
    for tag in known_tags or set():
        if tag and tag.lower() in lower_text:
            tags.add(_normalize_tag(tag))

    return ExtractedMetadata(
        tags=tuple(sorted(tag for tag in tags if tag)[:max_tags]),
        entities=tuple(sorted(entity for entity in entities if entity)[:max_entities]),
        extraction_notes=tuple(notes),
    )


def _normalize_tag(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().replace("_", "-")).strip()


def _capitalized_phrases(text: str) -> set[str]:
    # One to six capitalized/acronym/code-ish tokens.  This catches names like
    # "Blue Ridge Utility Van" without knowing anything about vehicles.
    pattern = re.compile(
        r"\b(?:[A-Z][A-Za-z0-9]*(?:[-'][A-Z]?[A-Za-z0-9]+)*|[A-Z]{2,})(?:\s+"
        r"(?:[A-Z][A-Za-z0-9]*(?:[-'][A-Z]?[A-Za-z0-9]+)*|[A-Z]{2,})){0,5}\b"
    )
    ignored = {"User", "Hermes"}
    return {
        match.group(0).strip() for match in pattern.finditer(text) if match.group(0) not in ignored
    }
