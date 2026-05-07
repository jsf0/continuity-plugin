"""Deterministic MVP extractors for corpus ingestion."""

from __future__ import annotations

import re
from typing import ClassVar

from continuity.ingest.models import (
    CandidateRecord,
    SourceDocument,
    SourceRef,
    SourceSegment,
    stable_id,
)

_COMMAND_RE = re.compile(r"`([^`]*(?:pytest|ruff)[^`]*)`")
_RELEASE_WORDS = {"release", "checklist", "deploy", "deployment", "procedure", "workflow"}
_PROCEDURE_VERBS = ("run ", "build ", "inspect ", "deploy ", "test ", "check ")


class ProjectCapsuleExtractor:
    """Create a compact project capsule from README-like segments."""

    name = "project-capsule"

    def extract(self, segment: SourceSegment, document: SourceDocument) -> list[CandidateRecord]:
        relative_path = str(document.metadata.get("relative_path") or document.title or "")
        if relative_path.lower() not in {"readme.md", "readme.txt", "readme.rst"}:
            return []
        project = document.scope_project or document.collection or document.title or "corpus"
        summary = _first_sentence_or_line(segment.text)
        return [
            CandidateRecord(
                candidate_id=stable_id(self.name, segment.segment_id, project),
                kind="artifact_summary",
                title=f"Project capsule: {project}",
                summary=summary,
                details=f"Derived from {relative_path or document.uri}.",
                scope_project=document.scope_project,
                scope_repo=document.scope_repo,
                scope_user=document.scope_user,
                scope_profile=document.scope_profile,
                tags=["project-capsule", "corpus-ingestion"],
                entities=[project],
                confidence=0.76,
                importance=0.78,
                trust_level="corpus_distilled",
                source_refs=[_source_ref(document, segment)],
                ingestion={"extractor": self.name},
            )
        ]


class ProcedureCandidateExtractor:
    """Detect checklist/procedure-like source segments."""

    name = "procedure-candidate"

    def extract(self, segment: SourceSegment, document: SourceDocument) -> list[CandidateRecord]:
        haystack = f"{segment.title or ''}\n{segment.text}".lower()
        if not any(word in haystack for word in _RELEASE_WORDS):
            return []
        if not any(verb in haystack for verb in _PROCEDURE_VERBS):
            return []
        title = segment.title or document.title or "Procedure"
        tags = ["procedure", "skill-candidate"]
        if "release" in haystack:
            tags.append("release")
        elif "deploy" in haystack:
            tags.append("deployment")
        summary = _compact_lines(segment.text, max_lines=4)
        return [
            CandidateRecord(
                candidate_id=stable_id(self.name, segment.segment_id, title),
                kind="procedure_candidate",
                title=f"Procedure candidate: {title}",
                summary=summary,
                details=f"Potential repeatable workflow extracted from {document.uri}.",
                scope_project=document.scope_project,
                scope_repo=document.scope_repo,
                scope_user=document.scope_user,
                scope_profile=document.scope_profile,
                tags=tags,
                entities=[title],
                confidence=0.74,
                importance=0.75,
                trust_level="corpus_distilled",
                source_refs=[_source_ref(document, segment)],
                ingestion={"extractor": self.name},
            )
        ]


class CodeOrConfigFactExtractor:
    """Extract obvious codebase command facts from source segments."""

    name = "code-or-config-fact"

    def extract(self, segment: SourceSegment, document: SourceDocument) -> list[CandidateRecord]:
        candidates: list[CandidateRecord] = []
        seen: set[str] = set()
        for command in _COMMAND_RE.findall(segment.text):
            command = command.strip()
            if not command or command in seen:
                continue
            seen.add(command)
            if "pytest" in command:
                label = "Test command"
                tags = ["codebase-map", "test-command"]
                importance = 0.68
            elif "ruff" in command:
                label = "Lint command"
                tags = ["codebase-map", "lint-command"]
                importance = 0.62
            else:
                continue
            candidates.append(
                CandidateRecord(
                    candidate_id=stable_id(self.name, segment.segment_id, command),
                    kind="codebase_fact",
                    title=f"{label}: {command}",
                    summary=f"The corpus documents `{command}` as a {label.lower()} for this project.",
                    details=f"Extracted from {document.uri}.",
                    scope_project=document.scope_project,
                    scope_repo=document.scope_repo,
                    scope_user=document.scope_user,
                    scope_profile=document.scope_profile,
                    tags=tags,
                    entities=[command],
                    confidence=0.78,
                    importance=importance,
                    trust_level="corpus_distilled",
                    source_refs=[_source_ref(document, segment)],
                    ingestion={"extractor": self.name},
                )
            )
        return candidates


class ManPageFactExtractor:
    """Extract compact records from rendered manual-page sections."""

    name = "manpage-fact"
    useful_sections: ClassVar[set[str]] = {
        "NAME",
        "SYNOPSIS",
        "DESCRIPTION",
        "FILES",
        "EXIT STATUS",
        "EXAMPLES",
        "CAVEATS",
        "BUGS",
    }

    def extract(self, segment: SourceSegment, document: SourceDocument) -> list[CandidateRecord]:
        if segment.kind != "manpage_section":
            return []
        section = str(segment.metadata.get("manpage_section") or segment.title or "").upper()
        if section not in self.useful_sections:
            return []
        manpage_name = str(segment.metadata.get("manpage_name") or _manpage_name(document))
        summary = _compact_lines(segment.text, max_lines=3)
        if not summary:
            return []
        kind = "glossary_term" if section == "NAME" else "codebase_fact"
        tags = ["manpage", "manual-section", section.lower().replace(" ", "-")]
        return [
            CandidateRecord(
                candidate_id=stable_id(self.name, segment.segment_id, section, manpage_name),
                kind=kind,
                title=f"Manpage {section}: {manpage_name}",
                summary=summary,
                details=f"Extracted from {document.uri} section {section}.",
                scope_project=document.scope_project,
                scope_repo=document.scope_repo,
                scope_user=document.scope_user,
                scope_profile=document.scope_profile,
                tags=tags,
                entities=[manpage_name, section],
                confidence=0.82,
                importance=0.62,
                trust_level="corpus_distilled",
                source_refs=[_source_ref(document, segment)],
                ingestion={"extractor": self.name},
            )
        ]


class EvalCaseGenerator:
    """Generate simple positive retrieval eval cases from candidate records."""

    name = "eval-generator"

    def generate(self, candidate: CandidateRecord) -> dict[str, object]:
        return {
            "eval_id": stable_id(self.name, candidate.candidate_id),
            "query": f"What should I know about {candidate.title}?",
            "expected_record_titles": [candidate.title],
            "expected_tags": candidate.tags,
            "forbidden_tags": [],
            "scope_project": candidate.scope_project,
            "source_candidate_ids": [candidate.candidate_id],
        }


def _source_ref(document: SourceDocument, segment: SourceSegment) -> SourceRef:
    metadata: dict[str, object] = {}
    context = segment.metadata.get("context")
    if isinstance(context, dict) and context.get("labels"):
        metadata["context"] = dict(context)
    outbound_references = segment.metadata.get("outbound_references")
    if isinstance(outbound_references, list) and outbound_references:
        metadata["outbound_references"] = [
            dict(reference) for reference in outbound_references if isinstance(reference, dict)
        ]
    return SourceRef(
        type="file" if document.uri.startswith("file://") else document.source_type,
        uri=document.uri,
        path=str(document.metadata.get("path")) if document.metadata.get("path") else None,
        segment_id=segment.segment_id,
        section=segment.title,
        line_start=segment.location.line_start if segment.location else None,
        line_end=segment.location.line_end if segment.location else None,
        content_hash=str(segment.metadata.get("content_hash"))
        if segment.metadata.get("content_hash")
        else None,
        metadata=metadata,
    )


def _first_sentence_or_line(text: str) -> str:
    compact = " ".join(text.split())
    sentence_match = re.match(r"(.+?[.!?])(?:\s|$)", compact)
    if sentence_match:
        return sentence_match.group(1)
    return compact[:240]


def _compact_lines(text: str, *, max_lines: int) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines[:max_lines])


def _manpage_name(document: SourceDocument) -> str:
    title = document.title or document.source_id.rsplit("/", 1)[-1]
    return re.sub(r"\.[1-9](?:\.in|\.txt)?$", "", title)
