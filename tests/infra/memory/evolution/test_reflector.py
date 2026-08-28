"""自进化记忆——夜间反思管线测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.infra.memory.evolution import reflector


def _dt(**kw):
    return datetime.now(timezone.utc) - timedelta(**kw)


class _FakeFind:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, n):
        return self

    async def to_list(self, length=None):
        return self._docs


class _FakeFeedbackCol:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query, *_a, **_k):
        return _FakeFind([d for d in self._docs if d.get("user_id") == query.get("user_id")])


class _FakeTracesCol:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query, *_a, **_k):
        uid = query.get("user_id")
        return _FakeFind([d for d in self._docs if d.get("user_id") == uid])


@pytest.fixture(autouse=True)
def _exchange_stub(monkeypatch):
    async def fake_load(run_id):
        if run_id == "r-down":
            return "帮我写个部署脚本", "好的，这是一个 3000 字的详细教程……（非常啰嗦）"
        if run_id == "r-fail":
            return "查一下今天的天气", ""
        return "用户消息", "助手回复"

    monkeypatch.setattr(reflector, "_load_exchange", fake_load)


@pytest.mark.asyncio
async def test_collect_signals_down_and_failed(monkeypatch):
    monkeypatch.setattr(
        reflector,
        "_get_feedback_collection",
        lambda: _FakeFeedbackCol(
            [
                {
                    "user_id": "u1",
                    "run_id": "r-down",
                    "session_id": "s1",
                    "rating": "down",
                    "comment": "太啰嗦",
                    "created_at": _dt(hours=2),
                }
            ]
        ),
    )
    monkeypatch.setattr(
        reflector,
        "_get_traces_collection",
        lambda: _FakeTracesCol(
            [
                {
                    "user_id": "u1",
                    "run_id": "r-fail",
                    "session_id": "s2",
                    "status": "failed",
                    "started_at": _dt(hours=3),
                }
            ]
        ),
    )
    signals = await reflector.collect_signal_runs("u1")
    kinds = {s.run_id: s.kind for s in signals}
    assert kinds == {"r-down": "down", "r-fail": "failed"}
    assert signals[0].comment == "太啰嗦"


@pytest.mark.asyncio
async def test_reflect_happy_path_stores_lesson(monkeypatch):
    seen_updates = []

    class FakeCol:
        async def update_one(self, q, u):
            seen_updates.append((q, u))

    class FakeBackend:
        _collection = FakeCol()

        async def recall(self, uid, query, *a, **k):
            return {"memories": []}

        async def retain(self, uid, content, **kw):
            return {"success": True, "memory_id": "m-lesson-1"}

    class FakeBound:
        async def ainvoke(self, messages):
            class Resp:
                tool_calls = [
                    {
                        "name": "memory_retain",
                        "args": {
                            "content": "rule: 只给命令和一句话说明\nwhy: 用户差评太啰嗦\nhow_to_apply: 用户要脚本时输出命令块",
                            "context": "feedback_rule",
                            "title": "回复保持简洁",
                            "summary": "用户要求简洁回复",
                            "tags": ["简洁", "回复风格"],
                        },
                    }
                ]

            return Resp()

    class FakeModel:
        def bind_tools(self, _t):
            return FakeBound()

    FakeBackend._get_memory_model = staticmethod(lambda: FakeModel())
    sig = reflector.SignalRun(run_id="r-down", session_id="s1", kind="down", comment="太啰嗦")
    result = await reflector.reflect_on_run(FakeBackend(), "u1", sig)
    assert result == {"stored": 1}
    # source 打上 self_evolved 标签（面板透明可辨）
    assert any(u.get("$set", {}).get("source") == "self_evolved" for _, u in seen_updates)


@pytest.mark.asyncio
async def test_reflect_no_tool_call_skips(monkeypatch):
    class FakeBackend:
        async def recall(self, *a, **k):
            return {"memories": []}

        async def retain(self, *a, **k):
            raise AssertionError("不应写入")

    class FakeBound:
        async def ainvoke(self, messages):
            class Resp:
                tool_calls = []

            return Resp()

    class FakeModel:
        def bind_tools(self, _t):
            return FakeBound()

    FakeBackend._get_memory_model = staticmethod(lambda: FakeModel())
    sig = reflector.SignalRun(run_id="r-ok", session_id="s1", kind="down", comment=None)
    assert await reflector.reflect_on_run(FakeBackend(), "u1", sig) == {"stored": 0}


@pytest.mark.asyncio
async def test_reflect_quota_enforced(monkeypatch):
    monkeypatch.setattr(reflector, "reflect_on_run", None)  # 保护：误用会炸
    from src.infra.memory.evolution import reflector as r

    async def fake_collect(uid, **k):
        return [
            r.SignalRun(run_id=f"r{i}", session_id="s", kind="down", comment=None)
            for i in range(10)
        ]

    calls = []

    async def fake_reflect(backend, uid, sig):
        calls.append(sig.run_id)
        return {"stored": 1}

    monkeypatch.setattr(r, "collect_signal_runs", fake_collect)
    monkeypatch.setattr(r, "reflect_on_run", fake_reflect)
    out = await r.evolve_user(object(), "u1", max_per_night=3)
    assert out == {"stored": 3}
    assert calls == ["r0", "r1", "r2"]


@pytest.mark.asyncio
async def test_positive_sampling_rate(monkeypatch):
    assert 0 < reflector.POSITIVE_SAMPLE_RATE < 1
    # 确定性检查采样函数存在且可注入
    assert callable(reflector._should_sample_positive)


@pytest.mark.asyncio
async def test_down_signal_marked_processed(monkeypatch):
    """down 信号反思一次后打 evolution_processed，采集即排除（防调度重复反思）。"""
    store = {
        "docs": [
            {
                "user_id": "u1",
                "run_id": "r-x",
                "session_id": "s",
                "rating": "down",
                "comment": "c",
                "created_at": _dt(hours=1),
            }
        ]
    }
    updates = []

    class Col:
        def find(self, q, *_a, **_k):
            docs = [d for d in store["docs"] if not d.get("evolution_processed")]
            return _FakeFind(docs)

        async def update_one(self, q, u):
            updates.append(u)
            for d in store["docs"]:
                d.update(u.get("$set", {}))

    monkeypatch.setattr(reflector, "_get_feedback_collection", lambda: Col())
    monkeypatch.setattr(reflector, "_get_traces_collection", lambda: _FakeTracesCol([]))

    sigs = await reflector.collect_signal_runs("u1")
    assert len(sigs) == 1
    await reflector._mark_signal_processed(sigs[0], "u1")
    assert any(u.get("$set", {}).get("evolution_processed") is True for u in updates)
    again = await reflector.collect_signal_runs("u1")
    assert again == []


@pytest.mark.asyncio
async def test_llm_failure_does_not_mark_processed(monkeypatch):
    """反思 LLM 失败（skipped）不得标记信号已处理——失败≠已处理，信号不能白丢。"""
    from src.infra.memory.evolution import reflector as r

    marked = []

    async def fake_collect(uid, **k):
        return [r.SignalRun(run_id="r-down", session_id="s", kind="down", comment="c")]

    async def fake_reflect(backend, uid, sig):
        return {"stored": 0, "skipped": True}

    async def fake_mark(sig, uid):
        marked.append(sig.run_id)

    monkeypatch.setattr(r, "collect_signal_runs", fake_collect)
    monkeypatch.setattr(r, "reflect_on_run", fake_reflect)
    monkeypatch.setattr(r, "_mark_signal_processed", fake_mark)
    await r.evolve_user(object(), "u1")
    assert marked == []

    async def fake_reflect_ok(backend, uid, sig):
        return {"stored": 1}

    monkeypatch.setattr(r, "reflect_on_run", fake_reflect_ok)
    await r.evolve_user(object(), "u1")
    assert marked == ["r-down"]
