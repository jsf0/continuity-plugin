"""Mirror Hermes built-in memory writes into continuity records."""

from __future__ import annotations

import hashlib
import re

from .models import ContextRecord, SourceRef, utc_now
from .security import is_safe_memory_text, redact_sensitive_text, truncate_text

MIRROR_MAX_CHARS = 1200

_LESSON_TERMS = frozenset({"lesson", "gotcha", "pitfall", "beware", "workaround", "quirk"})
_DECISION_TERMS = frozenset({"decided", "declined", "chose", "decision"})
_PROJECT_TERMS = frozenset(
    {"uses", "project", "repo", "convention", "test", "verify", "build", "verification"}
)


def build_mirrored_memory_record(
    *,
    action: str,
    target: str,
    content: str,
    scope_project: str | None,
) -> ContextRecord | None:
    """Build a continuity record from a Hermes built-in memory write.

    Returns ``None`` when the target/action/content should not be mirrored or
    when sanitized text still contains obvious prompt-injection content.
    """

    normalized_target = target.strip().lower()
    normalized_action = action.strip().lower()
    if normalized_target not in {"user", "memory"}:
        return None
    if normalized_action not in {"add", "replace"}:
        return None
    sanitized = sanitize_memory_write_content(content)
    if not sanitized:
        return None
    if not is_safe_memory_text(sanitized):
        return None
    kind = classify_memory_write(normalized_target, sanitized, scope_project=scope_project)
    record_scope = _record_scope(normalized_target, sanitized, kind, scope_project)
    source = SourceRef(
        type="built_in_memory",
        id=normalized_target,
        label=f"Hermes memory {normalized_action}",
        created_at=utc_now(),
    )
    return ContextRecord.new(
        id=mirrored_memory_record_id(normalized_target, content),
        kind=kind,
        title=_title_for_target(normalized_target),
        summary=sanitized,
        scope_project=record_scope,
        tags=_tags_for_record(normalized_target, kind, sanitized),
        entities=_entities_for_record(sanitized),
        sources=[source],
        confidence=0.9,
        importance=0.75,
        trust_level="built_in_memory_mirror",
    )


def mirrored_memory_record_id(target: str, content: str) -> str:
    """Return stable mirror id for a memory target/content pair."""

    normalized_target = target.strip().lower()
    sanitized = sanitize_memory_write_content(content)
    normalized = normalize_memory_write_content(sanitized)
    digest = hashlib.sha256(f"{normalized_target}\0{normalized}".encode()).hexdigest()[:16]
    return f"mirror_{normalized_target}_{digest}"


def sanitize_memory_write_content(content: str) -> str:
    """Redact and truncate a built-in memory write before mirroring."""

    return truncate_text(redact_sensitive_text(content.strip()), max_chars=MIRROR_MAX_CHARS)


def normalize_memory_write_content(content: str) -> str:
    """Normalize memory content for stable hashing."""

    return re.sub(r"\s+", " ", content.strip().lower())


def classify_memory_write(target: str, content: str, *, scope_project: str | None) -> str:
    """Conservatively classify a built-in memory write into an allowed record kind."""

    normalized = content.lower()
    if target == "user":
        return "user_preference"
    if _contains_any(normalized, _LESSON_TERMS):
        return "lesson_learned"
    if _contains_any(normalized, _DECISION_TERMS):
        return "decision"
    if scope_project and _contains_any(normalized, _PROJECT_TERMS):
        return "project_convention"
    return "environment_fact"


def _record_scope(target: str, content: str, kind: str, scope_project: str | None) -> str | None:
    if target != "memory" or not scope_project:
        return None
    normalized = content.lower()
    if scope_project.lower() in normalized or kind in {
        "lesson_learned",
        "decision",
        "project_convention",
    }:
        return scope_project
    return None


def _title_for_target(target: str) -> str:
    if target == "user":
        return "Hermes user memory"
    return "Hermes global memory"


def _tags_for_record(target: str, kind: str, content: str) -> list[str]:
    normalized = content.lower()
    tags = {"built_in_memory", f"memory_target:{target}", kind}
    if "ford raptor" in normalized or "raptor" in normalized:
        tags.update({"vehicle", "towing", "tow", "truck", "boat", "trailer", "personal_setup"})
    if any(term in normalized for term in ("boat", "catamaran", "sailing", "sailboat")):
        tags.update({"boat", "sailing", "storage", "trailerable"})
    if "framework desktop" in normalized or "ryzen ai max" in normalized:
        tags.update({"hardware", "framework", "local_llm", "llama_cpp"})
    if "llama.cpp" in normalized or "llama-cpp" in normalized:
        tags.update({"llama_cpp", "local_llm"})
    if "guard-proxy" in normalized:
        tags.update({"guard-proxy", "rust", "proxy", "project_status"})
    return sorted(tags)


def _entities_for_record(content: str) -> list[str]:
    normalized = content.lower()
    entities: set[str] = set()
    if "2018 ford raptor" in normalized:
        entities.update({"2018 Ford Raptor", "Ford Raptor", "Raptor"})
    elif "ford raptor" in normalized or "raptor" in normalized:
        entities.update({"Ford Raptor", "Raptor"})
    if "framework desktop" in normalized:
        entities.add("Framework Desktop")
    if "ryzen ai max 395" in normalized:
        entities.add("Ryzen AI Max 395")
    if "guard-proxy" in normalized:
        entities.add("guard-proxy")
    if "catamaran" in normalized:
        entities.add("catamaran")
    return sorted(entities)


def _contains_any(text: str, terms: frozenset[str]) -> bool:
    return any(term in text for term in terms)
