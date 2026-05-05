from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "demo-retrieval.py"


def test_demo_retrieval_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--quiet"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "demo retrieval ok" in result.stdout


def test_demo_retrieval_script_prints_human_readable_summary() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Continuity demo retrieval" in result.stdout
    assert "Query checks" in result.stdout
    assert "Round-trip checks" in result.stdout
    assert "Dream/prune report" in result.stdout
    assert "demo retrieval ok" in result.stdout
