"""Source connectors for corpus ingestion."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path

from continuity.ingest.models import SourceDocument

_MANPAGE_SUFFIX_RE = re.compile(r"\.[1-9](?:\.in)?$")

_SOURCE_TYPES_BY_SUFFIX = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".rst": "rst",
}


def infer_source_type(path: Path) -> str:
    """Infer a coarse source type from a file path."""

    suffix = path.suffix.lower()
    if _MANPAGE_SUFFIX_RE.search(path.name.lower()):
        return "manpage"
    return _SOURCE_TYPES_BY_SUFFIX.get(suffix, "binary")


class LocalFilesConnector:
    """Discover local files and convert them into SourceDocument rows."""

    name = "local-files"

    def discover(
        self,
        root: str | Path,
        *,
        include: Iterable[str] | None = None,
        exclude: Iterable[str] | None = None,
        project: str | None = None,
        repo: str | None = None,
        collection: str | None = None,
    ) -> Iterable[SourceDocument]:
        root_path = Path(root)
        include_patterns = list(include or ["**/*"])
        exclude_patterns = list(exclude or [])

        candidates: dict[Path, None] = {}
        for pattern in include_patterns:
            for path in root_path.glob(pattern):
                if path.is_file():
                    candidates[path] = None

        for path in sorted(candidates, key=lambda item: item.relative_to(root_path).as_posix()):
            relative_path = path.relative_to(root_path).as_posix()
            if _matches_any(path, root_path, exclude_patterns):
                continue
            try:
                stat = path.stat()
                sha256 = _sha256_file(path)
            except OSError:
                continue
            uri = f"file://{relative_path}"
            yield SourceDocument(
                source_id=uri,
                source_type=infer_source_type(path),
                uri=uri,
                title=path.name,
                collection=collection,
                metadata={
                    "path": str(path),
                    "relative_path": relative_path,
                    "sha256": sha256,
                    "mtime": stat.st_mtime,
                    "size_bytes": stat.st_size,
                },
                scope_project=project,
                scope_repo=repo,
            )


def _matches_any(path: Path, root: Path, patterns: Iterable[str]) -> bool:
    relative_path = path.relative_to(root)
    return any(relative_path.match(pattern) for pattern in patterns)


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
