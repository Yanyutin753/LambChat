import json
from pathlib import Path

import yaml

FRONTEND_DIR = Path("frontend")
MAKEFILE_PATH = Path("Makefile")
LINT_WORKFLOW_PATH = Path(".github/workflows/lint.yml")


def _pnpm_base_version(version: str) -> str:
    return version.split("(", 1)[0]


def test_react_and_react_dom_are_locked_to_the_same_version() -> None:
    package_json = json.loads((FRONTEND_DIR / "package.json").read_text())
    pnpm_lock = yaml.safe_load((FRONTEND_DIR / "pnpm-lock.yaml").read_text())

    dependencies = package_json["dependencies"]
    assert dependencies["react"] == dependencies["react-dom"]
    assert not dependencies["react"].startswith("^")

    lock_dependencies = pnpm_lock["importers"]["."]["dependencies"]
    assert _pnpm_base_version(lock_dependencies["react"]["version"]) == _pnpm_base_version(
        lock_dependencies["react-dom"]["version"]
    )


def test_frontend_smoke_build_keeps_full_build_contract() -> None:
    package_json = json.loads((FRONTEND_DIR / "package.json").read_text())
    scripts = package_json["scripts"]

    assert scripts["build"] == "tsc -b && vite build"
    assert scripts["build:smoke"] == "tsc -b && vite build --mode smoke"

    vite_config = (FRONTEND_DIR / "vite.config.ts").read_text(encoding="utf-8")
    assert 'mode === "smoke"' in vite_config
    assert 'process.env.LAMBCHAT_SKIP_PWA === "true"' in vite_config
    assert "!skipPwaBuild &&" in vite_config

    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "frontend-build-smoke" in makefile
    assert "cd frontend && pnpm run build:smoke" in makefile


def test_frontend_production_build_is_exercised_in_ci() -> None:
    workflow = yaml.safe_load(LINT_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["frontend-build"]

    assert job["name"] == "Frontend Build"
    build_steps = [step for step in job["steps"] if step.get("name") == "Build frontend"]
    assert len(build_steps) == 1
    assert build_steps[0]["run"] == "pnpm run build"
    assert build_steps[0]["working-directory"] == "frontend"
    assert build_steps[0]["env"]["NODE_OPTIONS"] == "--max-old-space-size=4096"


def test_ci_quality_gates_cover_plugins_and_distribution() -> None:
    workflow = yaml.safe_load(LINT_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    ruff_runs = [step.get("run") for step in jobs["ruff"]["steps"]]
    assert "uv run ruff check src/ plugins/" in ruff_runs
    assert "uv run ruff format --check src/ plugins/" in ruff_runs

    mypy_runs = [step.get("run") for step in jobs["mypy"]["steps"]]
    assert "uv run mypy src/ plugins/" in mypy_runs

    wheel_runs = [step.get("run") for step in jobs["wheel-build"]["steps"]]
    assert "uv build --wheel" in wheel_runs


def test_production_dependencies_are_audited_in_ci() -> None:
    workflow = yaml.safe_load(LINT_WORKFLOW_PATH.read_text(encoding="utf-8"))
    audit_job = workflow["jobs"]["frontend-audit"]
    node_steps = [step for step in audit_job["steps"] if step.get("name") == "Setup Node.js"]
    audit_steps = [
        step for step in audit_job["steps"] if step.get("name") == "Audit production dependencies"
    ]

    assert len(node_steps) == 1
    assert "cache" not in node_steps[0]["with"]
    assert len(audit_steps) == 1
    assert audit_steps[0]["run"] == "pnpm audit --prod --audit-level high"
    assert audit_steps[0]["working-directory"] == "frontend"
