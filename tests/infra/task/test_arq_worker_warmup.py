"""worker 启动预热已启用模型的 LLM 客户端。

生产测量（2026-09-17 yang）：worker 冷启动后每个模型的第一个请求要现场
创建模型实例（含 api_key 查库/Fernet 解密），TaskGroup 段 ~0.8s。启动后
后台预热已启用模型，客户端进 LLMClient 进程级 LRU，首个请求直接复用。
"""

from __future__ import annotations

from types import SimpleNamespace

from src.infra.task.arq_worker import _schedule_model_warmup, _warmup_model_clients
from src.kernel.config import settings


def _fake_config(value: str) -> SimpleNamespace:
    return SimpleNamespace(value=value, enabled=True)


async def test_warmup_precreates_clients_for_enabled_models(monkeypatch) -> None:
    created: list[str] = []

    async def fake_list_models(self, include_disabled=False):  # noqa: ANN001, ARG002
        return [_fake_config("gpt-6-astra"), _fake_config("deepseek-flash")]

    async def fake_get_model(**kwargs):  # noqa: ANN003
        created.append(kwargs.get("model"))
        return SimpleNamespace(warm=True)

    from src.infra.agent import model_storage as storage_module
    from src.infra.llm.client import LLMClient

    monkeypatch.setattr(storage_module.ModelStorage, "list_models", fake_list_models)
    monkeypatch.setattr(LLMClient, "get_model", staticmethod(fake_get_model))

    await _warmup_model_clients()

    assert created == ["gpt-6-astra", "deepseek-flash"]


async def test_warmup_continues_when_single_model_fails(monkeypatch) -> None:
    created: list[str] = []

    async def fake_list_models(self, include_disabled=False):  # noqa: ANN001, ARG002
        return [_fake_config("broken-one"), _fake_config("good-two")]

    async def fake_get_model(**kwargs):  # noqa: ANN003
        model = kwargs.get("model")
        created.append(model)
        if model == "broken-one":
            raise RuntimeError("bad config")
        return SimpleNamespace(warm=True)

    from src.infra.agent import model_storage as storage_module
    from src.infra.llm.client import LLMClient

    monkeypatch.setattr(storage_module.ModelStorage, "list_models", fake_list_models)
    monkeypatch.setattr(LLMClient, "get_model", staticmethod(fake_get_model))

    await _warmup_model_clients()

    assert created == ["broken-one", "good-two"]


async def test_warmup_listing_failure_is_swallowed(monkeypatch) -> None:
    async def fake_list_models(self, include_disabled=False):  # noqa: ANN001, ARG002
        raise RuntimeError("db down")

    calls: list[str] = []

    async def spy_get_model(**kwargs):  # noqa: ANN003
        calls.append(kwargs.get("model"))
        return SimpleNamespace(warm=True)

    from src.infra.agent import model_storage as storage_module
    from src.infra.llm.client import LLMClient

    monkeypatch.setattr(storage_module.ModelStorage, "list_models", fake_list_models)
    monkeypatch.setattr(LLMClient, "get_model", staticmethod(spy_get_model))

    await _warmup_model_clients()  # 不应上抛

    assert calls == []


async def test_schedule_model_warmup_respects_setting(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_MODEL_WARMUP_ON_STARTUP", False, raising=False)
    assert _schedule_model_warmup() is None

    monkeypatch.setattr(settings, "LLM_MODEL_WARMUP_ON_STARTUP", True, raising=False)
    task = _schedule_model_warmup()
    assert task is not None
    await task
