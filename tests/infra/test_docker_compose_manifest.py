from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_compose() -> dict:
    return yaml.safe_load((ROOT / "deploy/docker-compose.yml").read_text(encoding="utf-8"))


def _env_map(service: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in service.get("environment", []):
        if not isinstance(item, str) or "=" not in item:
            continue
        key, value = item.split("=", 1)
        result[key] = value
    return result


def test_docker_compose_enables_redis_backed_embedded_arq_worker() -> None:
    compose = _load_compose()
    lambchat = compose["services"]["lambchat"]
    env = _env_map(lambchat)

    assert env["REDIS_URL"] == "redis://redis:6379/0"
    assert env["TASK_BACKEND"] == "arq"
    assert env["ARQ_EMBEDDED_WORKER"] == "true"
    assert env["ARQ_QUEUE_NAME"] == "lambchat:arq"


def test_docker_compose_persists_plugin_data_for_plugin_runtime() -> None:
    compose = _load_compose()
    lambchat = compose["services"]["lambchat"]

    assert "plugin-data:/app/plugin-data" in lambchat["volumes"]
    assert "plugin-data" in compose["volumes"]


def test_dockerfile_bundles_system_plugins_for_container_runtime() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY plugins/ ./plugins/" in dockerfile


def test_dockerfile_exposes_plugin_locale_sources_to_frontend_build() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY frontend/ ./" in dockerfile
    assert "COPY plugins/ ../plugins/" in dockerfile
    assert "COPY plugin-data/ ../plugin-data/" in dockerfile
    assert dockerfile.index("COPY plugins/ ../plugins/") < dockerfile.index("RUN pnpm run build")
    assert dockerfile.index("COPY plugin-data/ ../plugin-data/") < dockerfile.index(
        "RUN pnpm run build"
    )


def test_python_wheel_bundles_plugin_backend_namespace() -> None:
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "src",
        "plugins",
    ]
