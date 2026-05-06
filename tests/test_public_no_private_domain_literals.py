from __future__ import annotations

from pathlib import Path

PUBLIC_CODE_DIR = Path(__file__).resolve().parents[1] / "continuity"

# These literals came from one user's live memories/projects and must not be
# required by generic retrieval or mirroring code. Tests and docs may discuss
# historical regressions, but the public plugin package itself must stay
# domain-neutral.
FORBIDDEN_PUBLIC_CODE_LITERALS = {
    "ford raptor",
    "raptor",
    "framework desktop",
    "ryzen ai max",
    "hobie",
    "catalina",
    "spruce run",
    "round valley",
    "guard-proxy",
    "spki",
    "reqwest",
    "rustls",
    "nemotron",
}


def test_public_plugin_code_does_not_embed_private_domain_literals() -> None:
    offenders: list[str] = []
    for path in sorted(PUBLIC_CODE_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for literal in sorted(FORBIDDEN_PUBLIC_CODE_LITERALS):
            if literal in text:
                offenders.append(f"{path.relative_to(PUBLIC_CODE_DIR.parent)}: {literal}")

    assert offenders == []
