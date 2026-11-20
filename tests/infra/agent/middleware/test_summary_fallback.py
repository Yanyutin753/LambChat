import pytest


@pytest.mark.asyncio
async def test_summarize_with_fallback_neutralizes_fractional_keep(monkeypatch) -> None:
    """生产 2026-11-20：fallback 模型无 profile，fractional keep 让构造即抛 ValueError。"""
    from src.infra.agent.middleware import summary_fallback

    constructed: dict = {}

    class _FakeHelper:
        def __init__(self, model, **kwargs):
            constructed.update(kwargs)
            constructed["_model"] = model

        async def _acreate_summary(self, messages):
            return "ok"

    class _FakeLC:
        def __init__(self):
            self.SummarizationMiddleware = _FakeHelper

    class _FakeClient:
        @staticmethod
        async def get_model(model, thinking=None):
            return object()

    real_import = __import__

    def import_hook(nm, *a, **kw):
        if nm == "langchain.agents.middleware":
            return _FakeLC()
        if nm == "src.infra.llm.client":
            type_mod = type(real_import(nm, *a, **kw))
            mod = type_mod("src.infra.llm.client")
            mod.LLMClient = _FakeClient
            return mod
        return real_import(nm, *a, **kw)

    monkeypatch.setattr("builtins.__import__", import_hook)

    result = await summary_fallback._summarize_with_fallback(
        {
            "summary_prompt": "p",
            "keep": ("fraction", 0.10),
            "token_counter": lambda *a, **k: 0,
        },
        [],
        fallback_model="fallback-model",
        thinking=None,
    )

    assert result == "ok"
    # fraction keep 被替换为绝对值，不再触发无 profile 构造错误
    assert constructed["keep"] == ("messages", 6)
