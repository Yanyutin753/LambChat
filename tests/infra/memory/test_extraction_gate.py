"""记忆提取 System One 预门（extraction_gate.py）契约测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infra.memory import extraction, extraction_gate
from src.infra.memory.extraction import extract_session_memory
from src.kernel.config import settings


def _enable(monkeypatch, *, mode: str, threshold: float = 0.35):
    monkeypatch.setattr(settings, "MEMORY_EXTRACTION_SYSTEMONE_MODE", mode)
    monkeypatch.setattr(settings, "MEMORY_EXTRACTION_SYSTEMONE_GATE_THRESHOLD", threshold)
    monkeypatch.setattr(settings, "SYSTEMONE_API_BASE", "http://von.local")


def _judge_returning(value: float | None):
    calls: list[str] = []

    async def fake_judge(state, instructions, *, criteria=None, transport=None):
        calls.append(state)
        return value

    return fake_judge, calls


# ---------------------------------------------------------------------------
# evaluate_extraction_gate 单元行为
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_disabled_returns_none_without_call(monkeypatch):
    _enable(monkeypatch, mode="off")
    fake_judge, calls = _judge_returning(0.1)
    monkeypatch.setattr(extraction_gate, "judge_noul", fake_judge)

    result = await extraction_gate.evaluate_extraction_gate("s1", "名", "fast", [{"user": "hi"}])

    assert result is None
    assert calls == []


@pytest.mark.asyncio
async def test_gate_invalid_mode_treated_as_off(monkeypatch):
    _enable(monkeypatch, mode="sometimes")
    fake_judge, calls = _judge_returning(0.1)
    monkeypatch.setattr(extraction_gate, "judge_noul", fake_judge)

    assert await extraction_gate.evaluate_extraction_gate("s1", "名", "", []) is None
    assert calls == []


@pytest.mark.asyncio
async def test_gate_unconfigured_skips_judgment(monkeypatch):
    monkeypatch.setattr(settings, "MEMORY_EXTRACTION_SYSTEMONE_MODE", "gate")
    monkeypatch.setattr(settings, "SYSTEMONE_API_BASE", "")
    fake_judge, calls = _judge_returning(0.1)
    monkeypatch.setattr(extraction_gate, "judge_noul", fake_judge)

    assert await extraction_gate.evaluate_extraction_gate("s1", "名", "", []) is None
    assert calls == []


@pytest.mark.asyncio
async def test_shadow_mode_never_skips(monkeypatch):
    _enable(monkeypatch, mode="shadow")
    fake_judge, _ = _judge_returning(0.01)
    monkeypatch.setattr(extraction_gate, "judge_noul", fake_judge)

    result = await extraction_gate.evaluate_extraction_gate("s1", "名", "", [{"user": "闲聊"}])

    assert result is not None
    assert result.skip is False
    assert result.p_memorable == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_gate_mode_skips_below_threshold(monkeypatch):
    _enable(monkeypatch, mode="gate", threshold=0.35)
    fake_judge, _ = _judge_returning(0.2)
    monkeypatch.setattr(extraction_gate, "judge_noul", fake_judge)

    result = await extraction_gate.evaluate_extraction_gate("s1", "名", "", [{"user": "闲聊"}])

    assert result is not None
    assert result.skip is True


@pytest.mark.asyncio
async def test_gate_mode_keeps_at_or_above_threshold(monkeypatch):
    _enable(monkeypatch, mode="gate", threshold=0.35)
    fake_judge, _ = _judge_returning(0.9)
    monkeypatch.setattr(extraction_gate, "judge_noul", fake_judge)

    result = await extraction_gate.evaluate_extraction_gate("s1", "名", "", [{"user": "要点"}])

    assert result is not None
    assert result.skip is False


@pytest.mark.asyncio
async def test_gate_failure_fails_open(monkeypatch):
    _enable(monkeypatch, mode="gate")
    fake_judge, _ = _judge_returning(None)
    monkeypatch.setattr(extraction_gate, "judge_noul", fake_judge)

    assert await extraction_gate.evaluate_extraction_gate("s1", "名", "", [{"user": "x"}]) is None


# ---------------------------------------------------------------------------
# 判定输入渲染
# ---------------------------------------------------------------------------


def test_render_gate_state_clips_to_budget():
    turns = [{"user": "u" * 500, "assistant": "a" * 500} for _ in range(60)]

    state = extraction_gate._render_gate_state("会话", "fast", turns)

    # 转录部分钳在预算内；上界额外容纳头部三行与其 join 分隔符
    header_len = len("Session: 会话") + len("Agent: fast") + len("Transcript:")
    assert len(state) <= extraction_gate._STATE_MAX_CHARS + 6 * 2 + header_len
    assert state.startswith("Session: 会话\n\nAgent: fast\n\nTranscript:")


# ---------------------------------------------------------------------------
# extract_session_memory 集成
# ---------------------------------------------------------------------------


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return self._docs


class FakeTracesCollection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query, projection=None):
        return FakeCursor(self._docs)


class FakeDb:
    def __init__(self, trace_docs):
        self._collections = {"traces": FakeTracesCollection(trace_docs)}

    def __getitem__(self, name):
        return self._collections[name]


class FakeMemoryCollection:
    def __init__(self):
        self.updates: list[tuple[dict, dict]] = []

    async def update_one(self, query, update):
        self.updates.append((query, update))
        return SimpleNamespace(modified_count=1)


class FakeBackend:
    name = "native"

    def __init__(self):
        self.retain_calls: list[dict] = []
        self._collection = FakeMemoryCollection()

    async def retain(self, user_id, content, **kwargs):
        self.retain_calls.append({"user_id": user_id, "content": content, **kwargs})
        return {"success": True, "memory_id": "m-1"}


def _trace_docs():
    return [
        {
            "run_id": "run-1",
            "started_at": "2026-09-01",
            "conversation_search": {
                "user_text": "随便聊聊今天天气",
                "assistant_final_text": "好的呀",
            },
        },
        {
            "run_id": "run-2",
            "started_at": "2026-09-02",
            "conversation_search": {"user_text": "嗯嗯", "assistant_final_text": "嗯"},
        },
    ]


@pytest.mark.asyncio
async def test_extract_skips_llm_when_gate_decides_not_memorable(monkeypatch):
    _enable(monkeypatch, mode="gate")
    fake_judge, _ = _judge_returning(0.05)
    monkeypatch.setattr(extraction_gate, "judge_noul", fake_judge)

    async def explode_model():
        raise AssertionError("LLM must not be invoked when gate skips")

    monkeypatch.setattr(extraction, "_get_extraction_model", explode_model)

    outcome = await extract_session_memory(
        FakeBackend(),
        FakeDb(_trace_docs()),
        "u1",
        {"session_id": "s1", "name": "闲聊", "metadata": {}},
    )

    assert outcome.status == "succeeded_no_output"


@pytest.mark.asyncio
async def test_extract_proceeds_when_gate_decides_memorable(monkeypatch):
    _enable(monkeypatch, mode="gate")
    fake_judge, _ = _judge_returning(0.9)
    monkeypatch.setattr(extraction_gate, "judge_noul", fake_judge)

    async def fake_model():
        return object()

    class FakeResponse:
        content = (
            '{"raw_memory":"### Task 1: 供应商\\ntask_outcome: partial\\nReusable knowledge:\\n- 九只鸭报价",'
            '"rollout_summary":"问询",'
            '"rollout_slug":"supplier",'
            '"title":"供应商",'
            '"summary":"九只鸭报价",'
            '"tags":["供应商"],'
            '"context":"project"}'
        )

    async def fake_ainvoke(model, messages, operation=None):
        return FakeResponse()

    monkeypatch.setattr(extraction, "_get_extraction_model", fake_model)
    import src.infra.llm.retry as retry_module

    monkeypatch.setattr(retry_module, "ainvoke_with_retry", fake_ainvoke)

    backend = FakeBackend()
    outcome = await extract_session_memory(
        backend, FakeDb(_trace_docs()), "u1", {"session_id": "s1", "name": "采购", "metadata": {}}
    )

    assert outcome.status == "succeeded"
    assert backend.retain_calls, "gate 放行后必须照常走 LLM 提取"


# ---------------------------------------------------------------------------
# context 域影子第二意见
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_shadow_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "MEMORY_EXTRACTION_SYSTEMONE_CONTEXT_SHADOW", False)

    async def explode(*args, **kwargs):
        raise AssertionError("关闭时不得调用 System One")

    monkeypatch.setattr(extraction_gate, "system_one", explode)
    await extraction_gate.log_context_second_opinion("s1", {"context": "project"}, "内容")


@pytest.mark.asyncio
async def test_context_shadow_logs_disagreement_without_rewrite(monkeypatch):
    monkeypatch.setattr(settings, "MEMORY_EXTRACTION_SYSTEMONE_CONTEXT_SHADOW", True)
    monkeypatch.setattr(settings, "SYSTEMONE_API_BASE", "http://von.local")

    captured: dict = {}

    async def fake_system_one(state, questions, **kwargs):
        captured["state"] = state
        return {"ctx": {"type": "choice", "choice": "reference", "confidence": 0.9}}

    monkeypatch.setattr(extraction_gate, "system_one", fake_system_one)
    # 只记日志：函数无返回值，不抛错即通过；断言 state 带上了索引字段
    await extraction_gate.log_context_second_opinion(
        "s1", {"context": "project", "title": "T", "summary": "S", "tags": ["a"]}, "RAW"
    )
    assert "Title: T" in captured["state"]
    assert "Summary: S" in captured["state"]
