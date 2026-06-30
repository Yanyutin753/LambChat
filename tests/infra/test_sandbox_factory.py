from __future__ import annotations

import pytest

from src.infra.sandbox.base import SandboxFactory, get_sandbox_config_from_settings


@pytest.fixture(autouse=True)
def _clear_sandbox_factory_registry() -> None:
    SandboxFactory._sandbox_registry.clear()
    SandboxFactory._run_id_to_sandbox.clear()


@pytest.mark.asyncio
async def test_close_sandbox_offloads_provider_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inside_blocking_io = False

    class _DaytonaProvider:
        __module__ = "daytona.fake"

        def __init__(self) -> None:
            self.deleted = False

        def delete(self) -> None:
            assert inside_blocking_io, "provider delete must be offloaded"
            self.deleted = True

    provider = _DaytonaProvider()
    SandboxFactory._sandbox_registry["sandbox-1"] = (object(), provider)

    async def _fake_run_blocking_io(func, /, *args, **kwargs):
        nonlocal inside_blocking_io
        assert inside_blocking_io is False
        inside_blocking_io = True
        try:
            return func(*args, **kwargs)
        finally:
            inside_blocking_io = False

    monkeypatch.setattr(
        "src.infra.sandbox.base.run_blocking_io",
        _fake_run_blocking_io,
        raising=False,
    )

    closed = await SandboxFactory.close_sandbox("sandbox-1")

    assert closed is True
    assert provider.deleted is True
    assert "sandbox-1" not in SandboxFactory._sandbox_registry


def test_cubesandbox_config_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.infra.sandbox.base.settings.SANDBOX_PLATFORM", "cubesandbox")
    monkeypatch.setattr("src.infra.sandbox.base.settings.CUBE_API_URL", "http://127.0.0.1:13000")
    monkeypatch.setattr("src.infra.sandbox.base.settings.CUBE_TEMPLATE", "tpl-cube")
    monkeypatch.setattr("src.infra.sandbox.base.settings.CUBE_PROXY_NODE_IP", "127.0.0.1")
    monkeypatch.setattr("src.infra.sandbox.base.settings.CUBE_PROXY_PORT_HTTP", 11080)
    monkeypatch.setattr("src.infra.sandbox.base.settings.CUBE_SANDBOX_DOMAIN", "cube.app")
    monkeypatch.setattr("src.infra.sandbox.base.settings.CUBE_TIMEOUT", 7200)
    monkeypatch.setattr("src.infra.sandbox.base.settings.CUBE_REQUEST_TIMEOUT", 180)
    monkeypatch.setattr("src.infra.sandbox.base.settings.CUBE_AUTO_PAUSE", True)
    monkeypatch.setattr("src.infra.sandbox.base.settings.CUBE_AUTO_RESUME", True)

    config = get_sandbox_config_from_settings()

    assert config.platform == "cubesandbox"
    assert config.api_url == "http://127.0.0.1:13000"
    assert config.template == "tpl-cube"
    assert config.proxy_node_ip == "127.0.0.1"
    assert config.proxy_port_http == 11080
    assert config.sandbox_domain == "cube.app"
    assert config.timeout == 7200
    assert config.request_timeout == 180
    assert config.auto_pause is True
    assert config.auto_resume is True
