"""追踪（Langfuse/LangSmith）配置生效链路：风险审查工单 1。

根因链：env 同步只在 Settings.__init__ 执行一次（import 期，早于 DB 设置
加载）→ 面板配置经 setattr 后永不回写 os.environ → tracer 门控的
os.getenv 恒空 → 追踪恒关；且 LangfuseTracer 首次评估后永久缓存。

修复契约：
- ``Settings.sync_tracing_env()`` 双向同步（关闭即清 env，不再单向）；
- ``initialize_settings()`` 在 DB 加载后重放同步（UI 配置 + 重启生效）；
- ``refresh_settings()`` 对追踪键重放同步并复位 tracer 缓存（运行时生效）。
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from src.infra.tracing.langfuse_client import LangfuseTracer, langfuse_tracer
from src.kernel.config import service as config_service
from src.kernel.config.base import Settings

TRACING_KEYS = (
    "LANGFUSE_ENABLED",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGSMITH_API_URL",
    "LANGSMITH_SAMPLE_RATE",
)


@pytest.fixture(autouse=True)
def _clean_tracing_env():
    saved = {key: os.environ.get(key) for key in TRACING_KEYS}
    for key in TRACING_KEYS:
        os.environ.pop(key, None)
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _make_settings(**overrides) -> Settings:
    values: dict = {
        "LANGFUSE_ENABLED": True,
        "LANGFUSE_PUBLIC_KEY": "pk-test",
        "LANGFUSE_SECRET_KEY": "sk-test",
        "LANGFUSE_HOST": "https://langfuse.example.com",
        "LANGSMITH_TRACING": True,
        "LANGSMITH_API_KEY": "lsv2-test",
        "LANGSMITH_PROJECT": "lambchat",
        "LANGSMITH_API_URL": "https://api.smith.langchain.com",
        "LANGSMITH_SAMPLE_RATE": 1.0,
    }
    values.update(overrides)
    settings = Settings()
    for key, value in values.items():
        setattr(settings, key, value)
    return settings


def test_sync_tracing_env_sets_env_when_enabled() -> None:
    _make_settings().sync_tracing_env()

    assert os.environ.get("LANGFUSE_ENABLED") == "true"
    assert os.environ.get("LANGFUSE_PUBLIC_KEY") == "pk-test"
    assert os.environ.get("LANGFUSE_SECRET_KEY") == "sk-test"
    assert os.environ.get("LANGFUSE_HOST") == "https://langfuse.example.com"
    assert os.environ.get("LANGSMITH_TRACING") == "true"
    assert os.environ.get("LANGSMITH_API_KEY") == "lsv2-test"


def test_sync_tracing_env_clears_env_when_disabled() -> None:
    # 单向同步的缺陷：UI 关闭后残留 env，tracer 依旧读到 true
    os.environ["LANGFUSE_ENABLED"] = "true"
    os.environ["LANGSMITH_TRACING"] = "true"

    _make_settings(LANGFUSE_ENABLED=False, LANGSMITH_TRACING=False).sync_tracing_env()

    assert "LANGFUSE_ENABLED" not in os.environ
    assert "LANGSMITH_TRACING" not in os.environ


def test_sync_tracing_env_clears_stale_keys_when_value_missing() -> None:
    os.environ["LANGFUSE_PUBLIC_KEY"] = "stale-pk"

    _make_settings(LANGFUSE_PUBLIC_KEY=None).sync_tracing_env()

    assert "LANGFUSE_PUBLIC_KEY" not in os.environ


def test_tracer_reset_re_enables_evaluation() -> None:
    tracer = LangfuseTracer()
    tracer._enabled = False
    tracer.reset()
    assert tracer._enabled is None

    os.environ["LANGFUSE_ENABLED"] = "true"
    os.environ["LANGFUSE_PUBLIC_KEY"] = "pk"
    os.environ["LANGFUSE_SECRET_KEY"] = "sk"
    try:
        assert tracer.enabled is True
    finally:
        for key in ("LANGFUSE_ENABLED", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
            os.environ.pop(key, None)


@pytest.mark.asyncio
async def test_initialize_settings_replays_tracing_env_sync(monkeypatch) -> None:
    """DB 加载后重放同步：UI 配置 + 重启后 os.environ 可用（工单 1 根因）。"""

    class _FakeStorage:
        async def get_all(self, admin_mode, mask_sensitive):
            assert admin_mode is True and mask_sensitive is False
            return {
                "tracing": [
                    SimpleNamespace(key="LANGFUSE_ENABLED", value=True),
                    SimpleNamespace(key="LANGFUSE_PUBLIC_KEY", value="pk-db"),
                    SimpleNamespace(key="LANGFUSE_SECRET_KEY", value="sk-db"),
                    SimpleNamespace(key="LANGFUSE_HOST", value="https://lf.db"),
                ]
            }

    class _FakeService:
        async def initialize(self):
            return None

        async def get_all(self, admin_mode, mask_sensitive):
            return await _FakeStorage().get_all(admin_mode, mask_sensitive)

    monkeypatch.setattr(
        "src.infra.settings.service.SettingsService.get_instance",
        staticmethod(lambda: _FakeService()),
    )
    monkeypatch.setattr(config_service, "_settings_service", _FakeService(), raising=False)

    try:
        await config_service.initialize_settings()

        assert os.environ.get("LANGFUSE_ENABLED") == "true"
        assert os.environ.get("LANGFUSE_PUBLIC_KEY") == "pk-db"
        assert getattr(config_service.settings, "LANGFUSE_ENABLED") is True
    finally:
        for key in TRACING_KEYS:
            os.environ.pop(key, None)


@pytest.mark.asyncio
async def test_refresh_settings_tracing_key_resets_tracer(monkeypatch) -> None:
    """运行时面板修改：env 重放 + tracer 复位，下次评估读到新值。"""

    class _FakeStorage:
        async def get_raw(self, key):
            return SimpleNamespace(key=key, value=True)

    monkeypatch.setattr(
        config_service,
        "_settings_service",
        SimpleNamespace(_storage=_FakeStorage()),
        raising=False,
    )
    reset_calls: list[bool] = []
    monkeypatch.setattr(langfuse_tracer, "reset", lambda: reset_calls.append(True))

    try:
        await config_service.refresh_settings("LANGFUSE_ENABLED")
        env_enabled = os.environ.get("LANGFUSE_ENABLED")
    finally:
        os.environ.pop("LANGFUSE_ENABLED", None)

    assert getattr(config_service.settings, "LANGFUSE_ENABLED") is True
    assert env_enabled == "true"
    assert reset_calls == [True]
