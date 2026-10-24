"""Keep the complete sharded suite behind the existing required check."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/lint.yml"


@pytest.mark.parametrize(
    ("suite", "command"),
    [
        ("frontend", "pnpm test --shard=${{ matrix.shard }}/4"),
        (
            "backend",
            "uv run python -m pytest -p scripts.pytest_shard --shard=${{ matrix.shard }}/4",
        ),
    ],
)
def test_ci_runs_all_shards_without_cancelling_siblings(suite, command):
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    shards = jobs[f"{suite}-test-shards"]
    assert shards["runs-on"] == "ubuntu-latest"
    assert shards["strategy"] == {
        "fail-fast": False,
        "matrix": {"shard": [1, 2, 3, 4]},
    }
    step = next(step for step in shards["steps"] if step.get("name") == f"Run {suite} tests")
    assert step["run"] == command
    if suite == "frontend":
        assert step["working-directory"] == "frontend"
    else:
        assert "redis" in shards["services"]
    assert not shards.get("continue-on-error", False)
    assert not step.get("continue-on-error", False)


@pytest.mark.parametrize("result", ["success", "failure", "cancelled", "skipped", ""])
@pytest.mark.parametrize("suite", ["frontend", "backend"])
def test_required_check_passes_only_when_every_shard_succeeds(result, suite):
    gate = yaml.safe_load(WORKFLOW.read_text())["jobs"][f"{suite}-tests"]
    assert gate["name"] == f"{suite.title()} Tests"
    assert gate["needs"] == [f"{suite}-test-shards"]
    assert gate["if"] == "${{ always() }}"
    step = gate["steps"][0]
    variable = f"{suite.upper()}_TEST_RESULT"
    assert step["env"] == {variable: "${{ needs." + suite + "-test-shards.result }}"}
    completed = subprocess.run(
        ["bash", "-c", step["run"]],
        env={**os.environ, variable: result},
        check=False,
    )
    assert (completed.returncode == 0) == (result == "success")


def test_native_verifier_uses_unoptimized_build_without_changing_shipped_app():
    jobs = yaml.safe_load((WORKFLOW.parent / "app-release.yml").read_text())["jobs"]
    steps = {step["name"]: step for step in jobs["desktop"]["steps"] if "name" in step}
    verifier = steps["Verify real native updater signature and version checks"]
    assert "--profile dev" in verifier["run"]
    assert "--release" not in verifier["run"]
    assert verifier["env"]["CARGO_PROFILE_DEV_DEBUG"] == "0"
    assert 'cargo test "${args[@]}"' in verifier["run"]
    assert 'cargo run "${args[@]}"' in verifier["run"]
    for name in (
        "Native Windows update installation regression",
        "Native macOS update installation regression",
    ):
        assert "/debug/examples/verify_updater" in steps[name]["run"]
    product = steps["Build desktop package with Tauri"]
    assert "CARGO_PROFILE_RELEASE_OPT_LEVEL" not in product["env"]
    assert "TAURI_DEBUG" not in product["env"]


def test_docker_manifest_publishes_all_tags_once_from_current_run(tmp_path):
    jobs = yaml.safe_load((WORKFLOW.parent / "docker-build.yml").read_text())["jobs"]
    step = next(
        step for step in jobs["merge"]["steps"] if step.get("name") == "Create and push manifest"
    )
    tags = ["ghcr.io/owner/image:develop", "ghcr.io/owner/image:develop-20261024-120000"]
    script = step["run"]
    for expression, value in {
        "steps.meta.outputs.tags": "\n".join(tags),
        "steps.image.outputs.name": "owner/image",
        "env.REGISTRY": "ghcr.io",
        "github.run_id": "12345",
    }.items():
        script = script.replace("${{ " + expression + " }}", value)
    docker = tmp_path / "docker"
    docker.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$MANIFEST_ARGS"\n')
    docker.chmod(0o755)
    output = tmp_path / "arguments"
    subprocess.run(
        ["bash", "-e", "-c", script],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "MANIFEST_ARGS": str(output),
        },
        check=True,
    )
    assert output.read_text().splitlines() == [
        "buildx",
        "imagetools",
        "create",
        "--tag",
        tags[0],
        "--tag",
        tags[1],
        "ghcr.io/owner/image:run-12345-amd64",
        "ghcr.io/owner/image:run-12345-arm64",
    ]
