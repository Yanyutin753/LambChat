import pytest

from src.infra.memory.client.native.backend import NativeMemoryBackend


@pytest.mark.asyncio
async def test_auto_retain_from_text_executes_llm_tool_call():
    seen: list[tuple[str, str | None, str | None, str | None]] = []

    class FakeBoundModel:
        async def ainvoke(self, _messages):
            class Response:
                tool_calls = [
                    {
                        "name": "memory_retain",
                        "args": {
                            "content": "I prefer DuckDB for local analytics work because it ships easily offline.",
                            "context": "user_identity",
                            "title": "DuckDB preference",
                            "summary": "Prefers DuckDB for local analytics.",
                        },
                    }
                ]

            return Response()

    class FakeModel:
        def bind_tools(self, _tools):
            return FakeBoundModel()

    backend = NativeMemoryBackend()

    async def fake_retain(
        user_id,
        content,
        context=None,
        title=None,
        summary=None,
        tags=None,
        existing_memory_id=None,
    ):
        seen.append((content, context, title, summary))
        return {"success": True, "memory_id": "m1"}

    async def fake_candidates(*_args, **_kwargs):
        return []

    backend.retain = fake_retain  # type: ignore[method-assign]
    backend._get_memory_model = staticmethod(lambda: FakeModel())  # type: ignore[method-assign]
    backend._get_auto_retain_candidates = fake_candidates  # type: ignore[method-assign]

    result = await backend.auto_retain_from_text(
        "u1",
        "I prefer DuckDB for local analytics work because it ships easily offline.",
    )

    assert result == {"success": True, "stored": 1, "candidates": 1}
    assert seen == [
        (
            "I prefer DuckDB for local analytics work because it ships easily offline.",
            "user_identity",
            "DuckDB preference",
            "Prefers DuckDB for local analytics.",
        )
    ]


@pytest.mark.asyncio
async def test_auto_retain_from_text_skips_when_llm_makes_no_tool_call():
    class FakeBoundModel:
        async def ainvoke(self, _messages):
            class Response:
                tool_calls = []

            return Response()

    class FakeModel:
        def bind_tools(self, _tools):
            return FakeBoundModel()

    backend = NativeMemoryBackend()
    backend._get_memory_model = staticmethod(lambda: FakeModel())  # type: ignore[method-assign]

    async def fake_candidates(*_args, **_kwargs):
        return []

    backend._get_auto_retain_candidates = fake_candidates  # type: ignore[method-assign]

    result = await backend.auto_retain_from_text("u1", "让我先看看 src/app.py 里的报错")

    assert result == {"success": True, "stored": 0, "candidates": 0}


@pytest.mark.asyncio
async def test_auto_retain_from_text_can_target_existing_memory_id():
    seen: list[tuple[str, str | None, str | None, str | None, str | None]] = []
    updates: list[tuple[dict, dict]] = []

    class FakeBoundModel:
        async def ainvoke(self, messages):
            prompt_text = str(messages[-1].content)
            assert "m-existing" in prompt_text

            class Response:
                tool_calls = [
                    {
                        "name": "memory_retain",
                        "args": {
                            "content": "User prefers DuckDB for offline analytics.",
                            "context": "user_identity",
                            "title": "DuckDB preference",
                            "summary": "Prefers DuckDB for offline analytics.",
                            "existing_memory_id": "m-existing",
                        },
                    }
                ]

            return Response()

    class FakeModel:
        def bind_tools(self, _tools):
            return FakeBoundModel()

    class FakeCollection:
        async def update_one(self, query, update):
            updates.append((query, update))

    backend = NativeMemoryBackend()

    async def fake_retain(
        user_id,
        content,
        context=None,
        title=None,
        summary=None,
        tags=None,
        existing_memory_id=None,
    ):
        seen.append((content, context, title, summary, existing_memory_id))
        return {"success": True, "memory_id": existing_memory_id or "m-new"}

    async def fake_candidates(*_args, **_kwargs):
        return [
            {
                "memory_id": "m-existing",
                "title": "DuckDB preference",
                "summary": "Prefers DuckDB for offline analytics.",
                "updated_at": "2026-04-02T00:00:00+00:00",
                "type": "user",
            }
        ]

    backend.retain = fake_retain  # type: ignore[method-assign]
    backend._collection = FakeCollection()
    backend._get_memory_model = staticmethod(lambda: FakeModel())  # type: ignore[method-assign]
    backend._get_auto_retain_candidates = fake_candidates  # type: ignore[method-assign]

    result = await backend.auto_retain_from_text(
        "u1",
        "I still prefer DuckDB for offline analytics work.",
    )

    assert result == {"success": True, "stored": 1, "candidates": 1}
    assert seen == [
        (
            "User prefers DuckDB for offline analytics.",
            "user_identity",
            "DuckDB preference",
            "Prefers DuckDB for offline analytics.",
            "m-existing",
        )
    ]
    assert updates == [
        (
            {"user_id": "u1", "memory_id": "m-existing"},
            {"$set": {"source": "auto_retained"}},
        )
    ]


@pytest.mark.asyncio
async def test_auto_retain_from_text_marks_new_memory_as_auto_retained():
    updates: list[tuple[dict, dict]] = []

    class FakeBoundModel:
        async def ainvoke(self, _messages):
            class Response:
                tool_calls = [
                    {
                        "name": "memory_retain",
                        "args": {
                            "content": "User prefers compact durable memory.",
                            "context": "feedback_rule",
                            "title": "Memory preference",
                            "summary": "Prefers compact durable memory.",
                            "tags": ["memory", "preference"],
                        },
                    }
                ]

            return Response()

    class FakeModel:
        def bind_tools(self, _tools):
            return FakeBoundModel()

    class FakeCollection:
        async def update_one(self, query, update):
            updates.append((query, update))

    backend = NativeMemoryBackend()

    async def fake_retain(*_args, **_kwargs):
        return {"success": True, "memory_id": "m-new"}

    async def fake_candidates(*_args, **_kwargs):
        return []

    backend.retain = fake_retain  # type: ignore[method-assign]
    backend._collection = FakeCollection()
    backend._get_memory_model = staticmethod(lambda: FakeModel())  # type: ignore[method-assign]
    backend._get_auto_retain_candidates = fake_candidates  # type: ignore[method-assign]

    result = await backend.auto_retain_from_text("u1", "I prefer compact durable memory.")

    assert result == {"success": True, "stored": 1, "candidates": 1}
    assert updates == [
        (
            {"user_id": "u1", "memory_id": "m-new"},
            {"$set": {"source": "auto_retained"}},
        )
    ]


@pytest.mark.asyncio
async def test_get_auto_retain_candidates_does_not_touch_access_stats(monkeypatch):
    from src.infra.memory.client.native import backend as backend_module

    backend = NativeMemoryBackend()

    async def fake_recall(*_args, **kwargs):
        assert kwargs["touch_access"] is False
        assert kwargs["enable_rerank"] is False
        return {
            "success": True,
            "query": "duckdb",
            "memories": [{"memory_id": "m1", "summary": "Prefers DuckDB", "type": "user"}],
            "search_mode": "text",
        }

    monkeypatch.setattr(backend_module, "recall_memories", fake_recall)

    candidates = await backend._get_auto_retain_candidates("u1", "duckdb")

    assert candidates == [{"memory_id": "m1", "summary": "Prefers DuckDB", "type": "user"}]


@pytest.mark.asyncio
async def test_auto_retain_prompt_frames_latest_exchange():
    captured: dict[str, str] = {}

    class FakeBoundModel:
        async def ainvoke(self, messages):
            captured["system"] = messages[0].content
            captured["human"] = messages[1].content

            class Response:
                tool_calls = []

            return Response()

    class FakeModel:
        def bind_tools(self, _tools):
            return FakeBoundModel()

    backend = NativeMemoryBackend()
    backend._get_memory_model = staticmethod(lambda: FakeModel())  # type: ignore[method-assign]

    async def fake_candidates(*_args, **_kwargs):
        return []

    backend._get_auto_retain_candidates = fake_candidates  # type: ignore[method-assign]

    result = await backend.auto_retain_from_text(
        "u1", "User:\n项目统一用 pnpm\n\nAssistant:\n好的，已记录。"
    )

    assert result == {"success": True, "stored": 0, "candidates": 0}
    # 决策提示词必须按"最近一轮交换"框定输入，并禁止记录助手泛泛回答
    assert "latest exchange" in captured["system"]
    assert "assistant's generic answer" in captured["system"]
    assert captured["human"].startswith("Latest exchange:\n")
    assert "User:\n项目统一用 pnpm" in captured["human"]
