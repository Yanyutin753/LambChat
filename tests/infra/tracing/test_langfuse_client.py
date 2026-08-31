from __future__ import annotations

"""Langfuse tracer 客户端：门控、handler 构造与 LangChain metadata 增强。

Langfuse v4 的 CallbackHandler 从 LangChain run metadata 中读取
langfuse_session_id / langfuse_user_id / langfuse_trace_name 三个特殊键，
其余 metadata 原样并入 trace，因此 LambChat 只需在既有 metadata 上追加
这三个键即可完成会话/用户维度的关联。
"""

from typing import Any

import pytest

from src.infra.tracing.langfuse_client import (
    LangfuseTracer,
    build_langfuse_metadata,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("LANGFUSE_ENABLED", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(key, raising=False)


def test_disabled_when_not_configured():
    assert LangfuseTracer().enabled is False
    assert LangfuseTracer().callback_handler() is None


def test_enabled_and_returns_handler_when_configured(monkeypatch):
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_HOST", "http://127.0.0.1:3000")
    tracer = LangfuseTracer()

    assert tracer.enabled is True
    handler = tracer.callback_handler()
    assert handler is not None
    from langfuse.langchain import CallbackHandler as LangchainCallbackHandler

    assert isinstance(handler, LangchainCallbackHandler)


def test_missing_secret_keeps_tracer_disabled(monkeypatch):
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    tracer = LangfuseTracer()
    assert tracer.enabled is False


def test_build_langfuse_metadata_adds_special_keys():
    base: dict[str, Any] = {"session_id": "s-1", "agent_name": "search"}
    enriched = build_langfuse_metadata(
        base,
        session_id="s-1",
        user_id="u-1",
        trace_name="search agent run",
    )

    assert enriched["langfuse_session_id"] == "s-1"
    assert enriched["langfuse_user_id"] == "u-1"
    assert enriched["langfuse_trace_name"] == "search agent run"
    # 原有 metadata 保留，且入参 dict 不被原地修改
    assert enriched["session_id"] == "s-1"
    assert enriched["agent_name"] == "search"
    assert "langfuse_session_id" not in base


def test_build_langfuse_metadata_skips_empty_values():
    enriched = build_langfuse_metadata({}, session_id=None, user_id="u-1", trace_name="")
    assert enriched == {"langfuse_user_id": "u-1"}


@pytest.mark.asyncio
async def test_settings_env_sync_for_langfuse(monkeypatch):
    """Settings 开启 Langfuse 后必须同步 os.environ（langfuse SDK 只认环境变量）。"""
    import os

    from src.kernel.config.base import Settings

    for key in ("LANGFUSE_ENABLED", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(key, raising=False)

    try:
        Settings(
            LANGFUSE_ENABLED=True,
            LANGFUSE_PUBLIC_KEY="pk-sync",
            LANGFUSE_SECRET_KEY="sk-sync",
            LANGFUSE_HOST="http://127.0.0.1:33000",
        )

        assert os.environ.get("LANGFUSE_PUBLIC_KEY") == "pk-sync"
        assert os.environ.get("LANGFUSE_SECRET_KEY") == "sk-sync"
        assert os.environ.get("LANGFUSE_HOST") == "http://127.0.0.1:33000"
    finally:
        # Settings 验证器直接写 os.environ，必须手动清理避免污染其他测试。
        for key in ("LANGFUSE_ENABLED", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
            os.environ.pop(key, None)


def test_agent_base_wires_langfuse_handler():
    """结构测试：BaseGraphAgent 必须在 Langfuse 启用时注入 CallbackHandler。"""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "agents"
        / "core"
        / "base.py"
    ).read_text(encoding="utf-8")

    assert "langfuse" in src
    assert "callback_handler" in src
