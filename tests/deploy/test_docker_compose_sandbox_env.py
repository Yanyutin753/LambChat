from pathlib import Path

import yaml


def test_compose_passes_e2b_settings_without_committed_secret() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load(
        (repository_root / "deploy/docker-compose.yml").read_text(encoding="utf-8")
    )
    environment = compose["services"]["lambchat"]["environment"]

    assert "E2B_API_KEY=${E2B_API_KEY:-}" in environment
    assert "E2B_TEMPLATE=${E2B_TEMPLATE:-base}" in environment

    example = (repository_root / "deploy/.env.example").read_text(encoding="utf-8")
    assert "E2B_API_KEY=" in example
    assert "E2B_TEMPLATE=base" in example
    assert "e2b_" not in example
