from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_llm_config_is_gitignored():
    ignored = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "configs/llm.yaml" in ignored


def test_ci_workflow_runs_pytest():
    workflow = ROOT / ".github" / "workflows" / "ci.yml"

    assert workflow.exists()
    assert "python -m pytest -q" in workflow.read_text(encoding="utf-8")
