"""Scope（归属边界）行为测试：写入推导、检索硬过滤、索引 revision、session 反查。

设计文档：docs/superpowers/specs/2026-09-04-memory-scope-and-context-design.md
"""

from datetime import datetime, timezone

import pytest

from src.infra.memory.client.native import indexing
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.memory.client.native.search import (
    build_scope_clause,
    format_memory,
    prioritize_sources,
)

# ---------------------------------------------------------------------------
# P0 scope 推导（纯函数）
# ---------------------------------------------------------------------------


def test_resolve_retain_scope_rejects_unknown_scope():
    from src.infra.memory.scope import ScopeResolutionError, resolve_retain_scope

    with pytest.raises(ScopeResolutionError):
        resolve_retain_scope(scope="global", project_id=None)


def test_resolve_retain_scope_rejects_project_scope_without_project_id():
    from src.infra.memory.scope import ScopeResolutionError, resolve_retain_scope

    with pytest.raises(ScopeResolutionError):
        resolve_retain_scope(scope="project", project_id=None)


def test_resolve_retain_scope_infers_project_from_explicit_project_id():
    from src.infra.memory.scope import resolve_retain_scope

    scope, project_id = resolve_retain_scope(scope=None, project_id="p1")

    assert scope == "project"
    assert project_id == "p1"


def test_resolve_retain_scope_ignores_project_context_without_project_id():
    """归属只认 project_id：context=project_* 但无归属证据 → 降级 user，不猜。"""
    from src.infra.memory.scope import resolve_retain_scope

    scope, project_id = resolve_retain_scope(scope=None, project_id=None)

    assert scope == "user"
    assert project_id is None


def test_resolve_retain_scope_project_context_with_project_id_becomes_project():
    from src.infra.memory.scope import resolve_retain_scope

    scope, project_id = resolve_retain_scope(scope=None, project_id="p1")

    assert scope == "project"
    assert project_id == "p1"


def test_resolve_retain_scope_clears_project_id_for_user_scope():
    from src.infra.memory.scope import resolve_retain_scope

    scope, project_id = resolve_retain_scope(scope="user", project_id="p1")

    assert scope == "user"
    assert project_id is None


# ---------------------------------------------------------------------------
# P0 retain 落库与 scope 内去重
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length):
        return self._docs[:length]


class _ScopeFakeCollection:
    """按查询形状分流：embedding 键=语义候选；否则=摘要候选。

    同时按查询中的 scope 去重边界过滤候选（模拟 Mongo 行为）：project 写入
    只见同项目候选，user 写入含 legacy 无 scope 文档。
    """

    def __init__(self, summary_docs, semantic_docs):
        self._summary_docs = summary_docs
        self._semantic_docs = semantic_docs
        self.find_queries: list[dict] = []
        self.inserted: list[dict] = []
        self.updated: list[tuple[dict, dict]] = []

    @staticmethod
    def _apply_scope_filter(query, docs):
        scope_cond = query.get("scope")
        if scope_cond is None:
            return docs
        if isinstance(scope_cond, dict) and "$in" in scope_cond:
            allowed = set(scope_cond["$in"])
            return [d for d in docs if d.get("scope") in allowed]
        expected_pid = query.get("project_id")
        return [
            d for d in docs if d.get("scope") == "project" and d.get("project_id") == expected_pid
        ]

    def find(self, query, _projection):
        self.find_queries.append(query)
        if "embedding" in query:
            return _FakeCursor(self._apply_scope_filter(query, self._semantic_docs))
        return _FakeCursor(self._apply_scope_filter(query, self._summary_docs))

    async def find_one(self, *_args, **_kwargs):
        return {"content_storage_mode": "inline", "content_store_key": None, "source_refs": []}

    async def update_one(self, query, payload):
        self.updated.append((query, payload))

    async def insert_one(self, doc):
        self.inserted.append(doc)


def _backend_with(collection) -> NativeMemoryBackend:
    backend = NativeMemoryBackend()

    async def fake_invalidate(_user_id):
        return None

    async def fake_embed(_text):
        return [1.0, 0.0]

    backend._collection = collection
    backend._invalidate_cache = fake_invalidate  # type: ignore[method-assign]
    backend._maybe_embed = fake_embed  # type: ignore[method-assign]
    return backend


@pytest.mark.asyncio
async def test_retain_rejects_project_scope_without_project_id():
    backend = _backend_with(_ScopeFakeCollection([], []))

    result = await backend.retain(
        "u1",
        "The project uses uv for all Python dependency management.",
        context="project_constraint",
        scope="project",
        title="uv deps",
        summary="Project uses uv for dependency management.",
        tags=["uv"],
    )

    assert result["success"] is False
    assert "project" in str(result.get("error", "")).lower()


@pytest.mark.asyncio
async def test_retain_persists_scope_and_project_id_on_insert():
    collection = _ScopeFakeCollection([], [])
    backend = _backend_with(collection)

    result = await backend.retain(
        "u1",
        "The LambChat project deploys via k8s with rolling updates and auto rollback.",
        context="project_constraint",
        project_id="proj-1",
        title="k8s deploys",
        summary="LambChat deploys via k8s with rollback.",
        tags=["k8s"],
    )

    assert result["success"] is True
    doc = collection.inserted[0]
    assert doc["scope"] == "project"
    assert doc["project_id"] == "proj-1"


@pytest.mark.asyncio
async def test_retain_defaults_to_user_scope_for_legacy_calls():
    collection = _ScopeFakeCollection([], [])
    backend = _backend_with(collection)

    result = await backend.retain(
        "u1",
        "The user prefers raw SQL over ORMs for all analytics workloads.",
        context="user_identity",
        title="raw SQL",
        summary="User prefers raw SQL for analytics.",
        tags=["sql"],
    )

    assert result["success"] is True
    doc = collection.inserted[0]
    assert doc["scope"] == "user"
    assert doc.get("project_id") is None


@pytest.mark.asyncio
async def test_retain_project_write_dedups_within_same_project_only():
    """项目记忆的语义去重候选必须限定在同一 project 内。"""
    now = datetime.now(timezone.utc)
    other_project = {
        "memory_id": "m-other",
        "memory_type": "project",
        "scope": "project",
        "project_id": "proj-2",
        "summary": "Project deploys via k8s.",
        "embedding": [1.0, 0.0],
        "updated_at": now,
    }
    collection = _ScopeFakeCollection([], [other_project])
    backend = _backend_with(collection)

    result = await backend.retain(
        "u1",
        "The project deploys via k8s with rolling updates.",
        context="project_constraint",
        project_id="proj-1",
        title="k8s deploys",
        summary="Project deploys via k8s with rollback.",
        tags=["k8s"],
    )

    assert result["success"] is True
    assert collection.inserted, "must NOT merge into another project's memory"
    assert collection.inserted[0]["memory_id"] != "m-other"
    semantic_query = next(q for q in collection.find_queries if "embedding" in q)
    assert semantic_query.get("scope") == "project"
    assert semantic_query.get("project_id") == "proj-1"


@pytest.mark.asyncio
async def test_retain_user_write_dedups_against_user_scope_and_legacy_docs():
    """user 写入的摘要候选包含 legacy 无 scope 文档（视同 user）。"""
    now = datetime.now(timezone.utc)
    legacy = {
        "memory_id": "m-legacy",
        "memory_type": "user",
        "summary": "Prefers raw SQL for analytics work.",
        "updated_at": now,
    }
    collection = _ScopeFakeCollection([legacy], [])
    backend = _backend_with(collection)

    result = await backend.retain(
        "u1",
        "The user now prefers DuckDB but still raw SQL for analytics queries.",
        context="user_identity",
        title="SQL preference",
        summary="Prefers raw SQL for analytics work.",
        tags=["sql"],
    )

    assert result["success"] is True
    assert result.get("updated_existing") is True
    summary_query = next(q for q in collection.find_queries if "embedding" not in q)
    assert summary_query.get("scope") == {"$in": ["user", None]}


@pytest.mark.asyncio
async def test_retain_update_sets_scope_fields_on_existing_memory():
    now = datetime.now(timezone.utc)
    existing = {
        "memory_id": "m1",
        "memory_type": "project",
        "summary": "Project deploys via k8s with rollback.",
        "updated_at": now,
        "scope": "project",
        "project_id": "proj-1",
    }
    collection = _ScopeFakeCollection([existing], [])
    backend = _backend_with(collection)

    result = await backend.retain(
        "u1",
        "The project deploys via k8s with rolling updates and auto rollback.",
        context="project_constraint",
        project_id="proj-1",
        title="k8s deploys",
        summary="Project deploys via k8s with rollback.",
        tags=["k8s"],
    )

    assert result["success"] is True
    assert result["updated_existing"] is True
    _query, payload = collection.updated[0]
    assert payload["$set"]["scope"] == "project"
    assert payload["$set"]["project_id"] == "proj-1"


# ---------------------------------------------------------------------------
# P1 检索硬过滤
# ---------------------------------------------------------------------------


def test_build_scope_clause_without_project_hides_project_memories():
    clause = build_scope_clause(None)

    assert clause == {"scope": {"$in": [None, "user", "reference"]}}


def test_build_scope_clause_with_project_includes_only_that_project():
    clause = build_scope_clause("proj-1")

    assert clause == {
        "$or": [
            {"scope": {"$in": [None, "user", "reference"]}},
            {"scope": "project", "project_id": "proj-1"},
        ]
    }


def test_prioritize_sources_prefers_current_project_scope():
    memories = [
        {"memory_id": "m-user", "source": "manual", "score": 0.9, "scope": "user"},
        {
            "memory_id": "m-proj",
            "source": "manual",
            "score": 0.5,
            "scope": "project",
            "project_id": "proj-1",
        },
    ]

    ranked = prioritize_sources(memories)

    assert ranked[0]["memory_id"] == "m-proj"


def test_format_memory_exposes_scope_fields():
    doc = {
        "memory_id": "m1",
        "user_id": "u1",
        "content": "Project uses uv.",
        "summary": "Project uses uv.",
        "title": "uv",
        "memory_type": "project",
        "source": "manual",
        "scope": "project",
        "project_id": "proj-1",
        "content_storage_mode": "inline",
        "created_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
    }

    memory = format_memory(doc, score=1.0, now=datetime(2026, 9, 2, tzinfo=timezone.utc))

    assert memory["scope"] == "project"
    assert memory["project_id"] == "proj-1"


@pytest.mark.asyncio
async def test_text_search_threads_scope_clause():
    from src.infra.memory.client.native import search as search_module

    queries: list[dict] = []

    class FakeCursor:
        def sort(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        async def to_list(self, length):
            # 非空结果：避免触发 keyword fallback 覆盖断言目标
            return [
                {
                    "memory_id": "m1",
                    "user_id": "u1",
                    "content": "k8s rollback",
                    "summary": "k8s rollback",
                    "title": "k8s",
                    "memory_type": "project",
                    "scope": "project",
                    "project_id": "proj-1",
                    "source": "manual",
                    "content_storage_mode": "inline",
                    "created_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
                    "updated_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
                }
            ]

    class FakeCollection:
        def find(self, query, *_a, **_k):
            queries.append(query)
            return FakeCursor()

    await search_module.text_search(
        collection=FakeCollection(),
        logger=object(),
        user_id="u1",
        query="k8s rollback",
        limit=5,
        memory_types=None,
        project_id="proj-1",
    )

    text_query = queries[0]
    assert "$text" in text_query
    assert text_query["$or"][1] == {"scope": "project", "project_id": "proj-1"}


@pytest.mark.asyncio
async def test_recall_memories_threads_project_id_to_all_paths(monkeypatch):
    from src.infra.memory.client.native import search as search_module

    seen: dict[str, object] = {}

    async def fake_text_search(
        collection,
        logger,
        user_id,
        query,
        limit,
        memory_types,
        context_filter=None,
        project_id=None,
    ):
        seen["text_project_id"] = project_id
        return []

    async def fake_vector_search(
        backend, user_id, query, limit, memory_types, context_filter=None, project_id=None
    ):
        seen["vector_project_id"] = project_id
        return []

    async def fake_fallback(
        collection, user_id, limit, memory_types, context_filter=None, project_id=None
    ):
        seen["fallback_project_id"] = project_id
        return []

    monkeypatch.setattr(search_module, "text_search", fake_text_search)
    monkeypatch.setattr(search_module, "vector_search", fake_vector_search)
    monkeypatch.setattr(search_module, "recent_context_fallback", fake_fallback)

    class FakeBackend:
        _embedding_fn = object()  # truthy：gather 同时走 vector_search 路径
        _logger = object()
        _collection = object()

        async def _update_access_stats(self, *_a, **_k):
            return None

    await search_module.recall_memories(
        FakeBackend(),  # type: ignore[arg-type]
        "u1",
        "project context overview",
        max_results=5,
        project_id="proj-1",
    )

    assert seen["text_project_id"] == "proj-1"
    assert seen["vector_project_id"] == "proj-1"
    assert seen["fallback_project_id"] == "proj-1"


# ---------------------------------------------------------------------------
# P2 索引 scope 过滤与 revision
# ---------------------------------------------------------------------------


def _index_doc(mid: str, mtype: str = "project", updated: datetime | None = None, **extra):
    doc = {
        "memory_id": mid,
        "title": f"title-{mid}",
        "index_label": f"label-{mid}",
        "summary": f"summary-{mid}",
        "updated_at": updated or datetime(2026, 9, 1, tzinfo=timezone.utc),
        "memory_type": mtype,
        "source": "manual",
        "context": "project_constraint",
    }
    doc.update(extra)
    return doc


def test_compute_index_revision_is_stable_and_sensitive():
    docs = [_index_doc("m1"), _index_doc("m2")]

    rev_same = indexing.compute_index_revision(docs)
    rev_shuffled = indexing.compute_index_revision(list(reversed(docs)))
    rev_changed = indexing.compute_index_revision(
        [_index_doc("m1"), _index_doc("m2", updated=datetime(2026, 9, 3, tzinfo=timezone.utc))]
    )

    assert rev_same == rev_shuffled
    assert rev_same != rev_changed
    assert len(rev_same) == 12


@pytest.mark.asyncio
async def test_build_memory_index_filters_by_scope_and_carries_revision():
    project_doc = _index_doc("m-proj", scope="project", project_id="proj-1")
    other_project_doc = _index_doc("m-other", scope="project", project_id="proj-2")
    user_doc = _index_doc("m-user", mtype="user", scope="user", context="user_identity")
    docs = [project_doc, other_project_doc, user_doc]

    seen: dict[str, object] = {}

    class FakeCursor:
        def __init__(self, result_docs):
            self._docs = result_docs

        def sort(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        async def to_list(self, length):
            return self._docs

    class FakeCollection:
        def find(self, query, _projection):
            seen["query"] = query
            scope_clause = query.get("$or")
            if scope_clause:
                allowed_project = scope_clause[1]["project_id"]
                docs_visible = [
                    d
                    for d in docs
                    if d.get("scope") in (None, "user", "reference")
                    or (d.get("scope") == "project" and d.get("project_id") == allowed_project)
                ]
            else:
                docs_visible = docs
            return FakeCursor(docs_visible)

    class FakeBackend:
        _collection = FakeCollection()
        _index_cache: dict = {}
        _INDEX_CACHE_MAX_SIZE = 1000

    result = await indexing.build_memory_index(FakeBackend(), "u1", project_id="proj-1")  # type: ignore[arg-type]

    assert "m-proj" in result or "label-m-proj" in result
    assert "m-other" not in result and "label-m-other" not in result
    assert "label-m-user" in result
    assert 'revision="' in result
    assert "$or" in seen["query"]


@pytest.mark.asyncio
async def test_build_memory_index_bytes_stable_across_rebuilds_with_same_data():
    """数据未变时两次构建（绕过缓存）字节一致——KV 缓存前缀纪律。"""
    docs = [
        _index_doc("m-proj", scope="project", project_id="proj-1"),
        _index_doc("m-user", mtype="user", scope="user", context="user_identity"),
    ]

    class FakeCursor:
        def __init__(self, result_docs):
            self._docs = result_docs

        def sort(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        async def to_list(self, length):
            return self._docs

    class FakeCollection:
        def find(self, *_a, **_k):
            return FakeCursor(docs)

    class FakeBackend:
        _collection = FakeCollection()
        _index_cache: dict = {}
        _INDEX_CACHE_MAX_SIZE = 1000

    first = await indexing.build_memory_index(FakeBackend(), "u1", project_id="proj-1")  # type: ignore[arg-type]
    second = await indexing.build_memory_index(FakeBackend(), "u1", project_id="proj-1")  # type: ignore[arg-type]

    assert first == second


# ---------------------------------------------------------------------------
# session → project 反查（scope.py）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_session_project_id_returns_metadata_project(monkeypatch):
    from src.infra.memory import scope as scope_module

    class FakeSessions:
        async def find_one(self, query, projection):
            assert query == {"session_id": "s1"}
            return {"metadata": {"project_id": "proj-1"}}

    class FakeDB:
        def __getitem__(self, _name):
            return FakeSessions()

    class FakeClient:
        def __getitem__(self, _name):
            return FakeDB()

    monkeypatch.setattr(scope_module, "_get_sessions_collection", lambda: FakeSessions())
    scope_module._SESSION_PROJECT_CACHE.clear()

    project_id = await scope_module.resolve_session_project_id("s1")

    assert project_id == "proj-1"
    assert "s1" in scope_module._SESSION_PROJECT_CACHE


@pytest.mark.asyncio
async def test_resolve_session_project_id_degrades_to_none_on_error(monkeypatch):
    from src.infra.memory import scope as scope_module

    class BrokenSessions:
        async def find_one(self, *_a, **_k):
            raise RuntimeError("mongo down")

    monkeypatch.setattr(scope_module, "_get_sessions_collection", lambda: BrokenSessions())
    scope_module._SESSION_PROJECT_CACHE.clear()

    assert await scope_module.resolve_session_project_id("s-broken") is None


@pytest.mark.asyncio
async def test_resolve_session_project_id_caches_within_ttl(monkeypatch):
    from src.infra.memory import scope as scope_module

    calls: list[str] = []

    class FakeSessions:
        async def find_one(self, query, projection):
            calls.append(str(query))
            return None

    monkeypatch.setattr(scope_module, "_get_sessions_collection", lambda: FakeSessions())
    scope_module._SESSION_PROJECT_CACHE.clear()

    await scope_module.resolve_session_project_id("s-cache")
    await scope_module.resolve_session_project_id("s-cache")

    assert len(calls) == 1
    scope_module._SESSION_PROJECT_CACHE.clear()


@pytest.mark.asyncio
async def test_resolve_session_project_id_none_for_empty_session():
    from src.infra.memory import scope as scope_module

    assert await scope_module.resolve_session_project_id(None) is None
    assert await scope_module.resolve_session_project_id("") is None
