from __future__ import annotations

from pathlib import Path

from continuity.ingest.connectors import LocalFilesConnector, infer_source_type

FIXTURE_ROOT = Path("tests/fixtures/ingestion/simple_docs")


def test_local_files_connector_discovers_included_files_with_metadata() -> None:
    documents = list(
        LocalFilesConnector().discover(
            FIXTURE_ROOT,
            include=["**/*.md"],
            exclude=["**/noisy.md"],
            project="continuity-ingestion-fixture",
            repo=str(FIXTURE_ROOT),
            collection="simple-docs",
        )
    )

    uris = {document.uri for document in documents}

    assert len(documents) == 5
    assert "file://README.md" in uris
    assert "file://docs/noisy.md" not in uris
    readme = next(document for document in documents if document.uri == "file://README.md")
    assert readme.source_id == "file://README.md"
    assert readme.source_type == "markdown"
    assert readme.title == "README.md"
    assert readme.collection == "simple-docs"
    assert readme.scope_project == "continuity-ingestion-fixture"
    assert readme.scope_repo == str(FIXTURE_ROOT)
    assert readme.metadata["path"].endswith("README.md")
    assert len(str(readme.metadata["sha256"])) == 64
    assert readme.metadata["size_bytes"] > 0


def test_local_files_connector_source_ids_are_stable_for_same_relative_path() -> None:
    first = list(LocalFilesConnector().discover(FIXTURE_ROOT, include=["README.md"]))
    second = list(LocalFilesConnector().discover(FIXTURE_ROOT, include=["README.md"]))

    assert [document.source_id for document in first] == [document.source_id for document in second]


def test_local_files_connector_sorts_documents_by_relative_path() -> None:
    documents = list(LocalFilesConnector().discover(FIXTURE_ROOT, include=["**/*.md"]))

    relative_paths = [document.metadata["relative_path"] for document in documents]

    assert relative_paths == sorted(relative_paths)


def test_infer_source_type_from_extension() -> None:
    assert infer_source_type(Path("README.md")) == "markdown"
    assert infer_source_type(Path("notes.txt")) == "text"
    assert infer_source_type(Path("guide.rst")) == "rst"
    assert infer_source_type(Path("unknown.bin")) == "binary"
