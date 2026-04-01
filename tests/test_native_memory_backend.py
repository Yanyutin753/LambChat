from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

os.environ["DEBUG"] = "false"

from src.infra.memory.client.native import NativeMemoryBackend
from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE
from src.infra.memory.tools import auto_retain_conversation
from src.kernel.config import settings


class FakeInsertManyResult:
    def __init__(self, inserted_ids: list[str]):
        self.inserted_ids = inserted_ids


class FakeCollection:
    def __init__(self, docs: list[dict] | None = None):
        self.docs = list(docs or [])
        self.inserted_docs: list[dict] = []
        self.updated_docs: list[tuple[dict, dict]] = []

    async def find_one(self, query: dict, projection: dict | None = None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                if projection:
                    return {key: doc[key] for key in projection if key in doc}
                return doc
        return None

    async def insert_one(self, doc: dict):
        self.docs.append(doc)
        self.inserted_docs.append(doc)
        return SimpleNamespace(inserted_id=doc["memory_id"])

    async def insert_many(self, docs: list[dict]):
        self.docs.extend(docs)
        self.inserted_docs.extend(docs)
        return FakeInsertManyResult([doc["memory_id"] for doc in docs])

    async def update_one(self, query: dict, update: dict):
        self.updated_docs.append((query, update))
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                if "$set" in update:
                    doc.update(update["$set"])
                if "$push" in update:
                    for key, value in update["$push"].items():
                        doc.setdefault(key, []).append(value)
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    async def delete_many(self, query: dict):
        before = len(self.docs)
        kept = []
        for doc in self.docs:
            ok = True
            for key, value in query.items():
                if isinstance(value, dict) and "$in" in value:
                    if doc.get(key) not in value["$in"]:
                        ok = False
                        break
                elif doc.get(key) != value:
                    ok = False
                    break
            if not ok:
                kept.append(doc)
        self.docs = kept
        deleted_count = before - len(self.docs)
        return SimpleNamespace(deleted_count=deleted_count)

    def find(self, query: dict, projection: dict | None = None):
        matched = []
        for doc in self.docs:
            ok = True
            for key, value in query.items():
                if isinstance(value, dict) and "$gte" in value:
                    if doc.get(key) < value["$gte"]:
                        ok = False
                        break
                elif isinstance(value, dict) and "$in" in value:
                    if doc.get(key) not in value["$in"]:
                        ok = False
                        break
                elif isinstance(value, dict) and "$ne" in value:
                    if doc.get(key) == value["$ne"]:
                        ok = False
                        break
                elif key == "$or":
                    sub_ok = False
                    for sub in value:
                        for sub_key, sub_value in sub.items():
                            if (
                                isinstance(sub_value, dict)
                                and "$regex" in sub_value
                                and sub_value["$regex"].lower() in str(doc.get(sub_key, "")).lower()
                            ):
                                sub_ok = True
                                break
                        if sub_ok:
                            break
                    if not sub_ok:
                        ok = False
                        break
                elif doc.get(key) != value:
                    ok = False
                    break
            if ok:
                if projection:
                    matched.append({k: doc[k] for k in projection if k in doc})
                else:
                    matched.append(doc)
        return FakeCursor(matched)

    def aggregate(self, pipeline: list[dict]):
        docs = list(self.docs)
        if pipeline and "$match" in pipeline[0]:
            match = pipeline[0]["$match"]
            filtered = []
            for doc in docs:
                ok = True
                for key, value in match.items():
                    if isinstance(value, dict) and "$ne" in value:
                        if doc.get(key) == value["$ne"]:
                            ok = False
                            break
                    elif doc.get(key) != value:
                        ok = False
                        break
                if ok:
                    filtered.append(doc)
            docs = filtered

        docs.sort(key=lambda doc: doc.get("updated_at"), reverse=True)
        grouped: dict[str, list[dict]] = {}
        for doc in docs:
            grouped.setdefault(doc.get("memory_type", "unknown"), []).append(
                {
                    "title": doc.get("title", ""),
                    "index_label": doc.get("index_label", ""),
                    "summary": doc.get("summary", ""),
                    "memory_id": doc.get("memory_id", ""),
                    "updated_at": doc.get("updated_at"),
                }
            )

        rows = [{"_id": key, "items": value[:5]} for key, value in grouped.items()]
        return FakeAggregateCursor(rows)


class FakeCursor:
    def __init__(self, docs: list[dict]):
        self.docs = docs

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, length: int):
        return self.docs[:length]


class FakeAggregateCursor:
    def __init__(self, docs: list[dict]):
        self.docs = docs

    async def to_list(self, length: int):
        return self.docs[:length]


class FakeStore:
    def __init__(self):
        self.put_calls: list[tuple[tuple[str, ...], str, dict]] = []
        self.items: dict[tuple[tuple[str, ...], str], dict] = {}

    def put(self, namespace: tuple[str, ...], key: str, value: dict):
        self.put_calls.append((namespace, key, value))
        self.items[(namespace, key)] = value

    def get(self, namespace: tuple[str, ...], key: str):
        value = self.items.get((namespace, key))
        if value is None:
            return None
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            namespace=namespace,
            key=key,
            value=value,
            created_at=now,
            updated_at=now,
        )


@pytest.mark.asyncio
async def test_auto_retain_skips_transient_status(monkeypatch):
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()

    async def fake_extract(user_id: str, conversation: str):
        return [
            {
                "content": "正在查看 definitions.py 并准备改一下。",
                "summary": "正在看配置文件",
                "title": "当前操作",
                "memory_type": "project",
                "tags": ["配置"],
            }
        ]

    monkeypatch.setattr(backend, "_llm_extract_memories", fake_extract)

    async def fake_embed(text: str):
        return None

    async def fake_invalidate(user_id: str):
        return None

    monkeypatch.setattr(backend, "_maybe_embed", fake_embed)
    monkeypatch.setattr(backend, "_invalidate_cache", fake_invalidate)

    async def fake_score(candidate: dict, existing_memory=None, manual: bool = False):
        return {"score": 0.1, "action": "skip", "memory_type": "project"}

    monkeypatch.setattr(backend, "_llm_score_memory_candidate", fake_score)
    monkeypatch.setattr(
        backend, "_llm_build_index_label", lambda title, summary, content: "当前操作"
    )

    await backend.auto_retain("user-1", "正在查看 definitions.py 并准备改一下。")

    assert backend._collection.inserted_docs == []


@pytest.mark.asyncio
async def test_auto_retain_logs_when_no_memories_extracted(monkeypatch, caplog):
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()

    async def fake_extract(user_id: str, conversation: str):
        return []

    monkeypatch.setattr(backend, "_llm_extract_memories", fake_extract)

    with caplog.at_level(logging.INFO):
        await backend.auto_retain("user-1", "我是杨洋，是一名程序员")

    assert "skip auto-retain: no extracted memories" in caplog.text


@pytest.mark.asyncio
async def test_auto_retain_logs_when_scoring_skips_candidate(monkeypatch, caplog):
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()

    async def fake_extract(user_id: str, conversation: str):
        return [
            {
                "content": "我是杨洋，是一名程序员，目前长期维护lambchat开源项目并负责核心功能开发。",
                "summary": "杨洋，程序员，维护lambchat项目",
                "title": "杨洋身份",
                "memory_type": "user",
                "tags": ["用户"],
            }
        ]

    async def fake_score(candidate: dict, existing_memory=None, manual: bool = False):
        return {"score": 0.2, "action": "skip", "memory_type": "user", "reason": "too_generic"}

    monkeypatch.setattr(backend, "_llm_extract_memories", fake_extract)
    monkeypatch.setattr(backend, "_llm_score_memory_candidate", fake_score)

    with caplog.at_level(logging.INFO):
        await backend.auto_retain(
            "user-1", "我是杨洋，是一名程序员，目前长期维护lambchat开源项目并负责核心功能开发。"
        )

    assert "skip candidate after scoring" in caplog.text
    assert "too_generic" in caplog.text


@pytest.mark.asyncio
async def test_auto_retain_logs_when_candidate_is_deduplicated(monkeypatch, caplog):
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()

    async def fake_extract(user_id: str, conversation: str):
        return [
            {
                "content": "我是杨洋，是一名程序员，目前长期维护lambchat开源项目并负责核心功能开发。",
                "summary": "杨洋，程序员，维护lambchat项目",
                "title": "杨洋身份",
                "memory_type": "user",
                "tags": ["用户"],
            }
        ]

    async def fake_score(candidate: dict, existing_memory=None, manual: bool = False):
        return {"score": 0.9, "action": "create", "memory_type": "user"}

    async def fake_dedup(user_id: str, candidates: list[dict]):
        return []

    monkeypatch.setattr(backend, "_llm_extract_memories", fake_extract)
    monkeypatch.setattr(backend, "_llm_score_memory_candidate", fake_score)
    monkeypatch.setattr(backend, "_deduplicate_against_existing", fake_dedup)

    with caplog.at_level(logging.INFO):
        await backend.auto_retain(
            "user-1", "我是杨洋，是一名程序员，目前长期维护lambchat开源项目并负责核心功能开发。"
        )

    assert "skip candidate after deduplication" in caplog.text


@pytest.mark.asyncio
async def test_auto_retain_appends_project_memory(monkeypatch):
    now = datetime.now(timezone.utc)
    existing = {
        "memory_id": "mem-1",
        "user_id": "user-1",
        "content": "项目约束：必须接入 StoreBackend 保存长文本。",
        "summary": "项目要求长文本走 StoreBackend",
        "title": "项目约束",
        "memory_type": "project",
        "context": "conversation_turn",
        "tags": ["项目", "存储"],
        "source": "auto_retained",
        "created_at": now,
        "updated_at": now,
        "accessed_at": now,
        "access_count": 0,
    }
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection([existing])

    async def fake_extract(user_id: str, conversation: str):
        return [
            {
                "content": "项目约束补充：过长记忆正文不要塞 Mongo，改存到 StoreBackend 文件中。",
                "summary": "补充长文本应外置存储",
                "title": "项目约束",
                "memory_type": "project",
                "tags": ["项目", "存储"],
            }
        ]

    monkeypatch.setattr(backend, "_llm_extract_memories", fake_extract)

    async def fake_embed(text: str):
        return None

    async def fake_invalidate(user_id: str):
        return None

    monkeypatch.setattr(backend, "_maybe_embed", fake_embed)
    monkeypatch.setattr(backend, "_invalidate_cache", fake_invalidate)

    async def fake_score(candidate: dict, existing_memory=None, manual: bool = False):
        return {"score": 0.92, "action": "append", "memory_type": "project"}

    async def fake_compose(existing_memory: dict, candidate: dict, action: str):
        return {
            "title": "项目约束",
            "summary": "统一长文本记忆存储策略",
            "content": "统一方案：长文本正文走 StoreBackend，Mongo 仅保留摘要、标题与引用。",
            "memory_type": "project",
        }

    monkeypatch.setattr(backend, "_llm_score_memory_candidate", fake_score)
    monkeypatch.setattr(backend, "_llm_compose_memory", fake_compose)
    monkeypatch.setattr(
        backend, "_llm_build_index_label", lambda title, summary, content: "长记忆策略"
    )

    await backend.auto_retain("user-1", "补充：长文本要走 StoreBackend 文件。")

    assert backend._collection.inserted_docs == []
    assert backend._collection.updated_docs, "expected append-style update instead of new insert"
    updated_doc = backend._collection.docs[0]
    assert updated_doc["summary"] == "统一长文本记忆存储策略"
    assert "Mongo 仅保留摘要" in updated_doc["content"]


@pytest.mark.asyncio
async def test_auto_retain_creates_memory_when_llm_allows(monkeypatch):
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()

    async def fake_extract(user_id: str, conversation: str):
        return [
            {
                "content": "项目要求：过长记忆正文统一外置到 StoreBackend，Mongo 只留摘要和引用。",
                "summary": "项目要求长记忆外置",
                "title": "记忆存储策略",
                "memory_type": "project",
                "tags": ["项目", "存储"],
            }
        ]

    async def fake_embed(text: str):
        return None

    async def fake_invalidate(user_id: str):
        return None

    async def fake_score(candidate: dict, existing_memory=None, manual: bool = False):
        return {"score": 0.88, "action": "create", "memory_type": "project"}

    monkeypatch.setattr(backend, "_llm_extract_memories", fake_extract)
    monkeypatch.setattr(backend, "_maybe_embed", fake_embed)
    monkeypatch.setattr(backend, "_invalidate_cache", fake_invalidate)
    monkeypatch.setattr(backend, "_llm_score_memory_candidate", fake_score)
    monkeypatch.setattr(
        backend, "_llm_build_index_label", lambda title, summary, content: "记忆策略"
    )

    await backend.auto_retain("user-1", "记忆策略：长文本外置。")

    assert len(backend._collection.inserted_docs) == 1


@pytest.mark.asyncio
async def test_auto_retain_skips_duplicate_create_candidate(monkeypatch):
    now = datetime.now(timezone.utc)
    existing = {
        "memory_id": "mem-dup",
        "user_id": "user-1",
        "content": "项目要求：过长记忆正文统一外置到 StoreBackend，Mongo 只留摘要和引用。",
        "summary": "项目要求长记忆外置",
        "title": "记忆存储策略",
        "memory_type": "project",
        "context": "conversation_turn",
        "tags": ["项目", "存储"],
        "source": "auto_retained",
        "created_at": now,
        "updated_at": now,
        "accessed_at": now,
        "access_count": 0,
    }
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection([existing])

    async def fake_extract(user_id: str, conversation: str):
        return [
            {
                "content": "项目要求：长记忆正文放到 StoreBackend，Mongo 只保留摘要和引用。",
                "summary": "项目要求长记忆外置",
                "title": "新的存储策略说法",
                "memory_type": "project",
                "tags": ["长期", "存储"],
            }
        ]

    async def fake_embed(text: str):
        return None

    async def fake_invalidate(user_id: str):
        return None

    async def fake_score(candidate: dict, existing_memory=None, manual: bool = False):
        return {"score": 0.9, "action": "create", "memory_type": "project"}

    monkeypatch.setattr(backend, "_llm_extract_memories", fake_extract)
    monkeypatch.setattr(backend, "_maybe_embed", fake_embed)
    monkeypatch.setattr(backend, "_invalidate_cache", fake_invalidate)
    monkeypatch.setattr(backend, "_llm_score_memory_candidate", fake_score)

    await backend.auto_retain("user-1", "同一条策略换个说法再来一次")

    assert backend._collection.inserted_docs == []


@pytest.mark.asyncio
async def test_replace_existing_memory_uses_llm_composed_content(monkeypatch):
    now = datetime.now(timezone.utc)
    existing = {
        "memory_id": "mem-2",
        "user_id": "user-1",
        "content": "旧策略：所有记忆都直接写 Mongo。",
        "summary": "旧的记忆存储策略",
        "title": "存储策略",
        "memory_type": "project",
        "context": "conversation_turn",
        "tags": ["项目", "存储"],
        "source": "auto_retained",
        "created_at": now,
        "updated_at": now,
        "accessed_at": now,
        "access_count": 0,
    }
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection([existing])

    async def fake_extract(user_id: str, conversation: str):
        return [
            {
                "content": "新策略：长文本正文走 StoreBackend，Mongo 只留摘要和引用。",
                "summary": "新的记忆存储策略",
                "title": "存储策略",
                "memory_type": "project",
                "tags": ["项目", "存储"],
            }
        ]

    async def fake_embed(text: str):
        return None

    async def fake_invalidate(user_id: str):
        return None

    async def fake_score(candidate: dict, existing_memory=None, manual: bool = False):
        return {"score": 0.95, "action": "replace", "memory_type": "project"}

    async def fake_compose(existing_memory: dict, candidate: dict, action: str):
        return {
            "title": "存储策略",
            "summary": "新版记忆存储策略",
            "content": "新版方案：长文本统一存入 StoreBackend，Mongo 仅保存摘要、标题和引用信息。",
            "memory_type": "project",
        }

    monkeypatch.setattr(backend, "_llm_extract_memories", fake_extract)
    monkeypatch.setattr(backend, "_maybe_embed", fake_embed)
    monkeypatch.setattr(backend, "_invalidate_cache", fake_invalidate)
    monkeypatch.setattr(backend, "_llm_score_memory_candidate", fake_score)
    monkeypatch.setattr(backend, "_llm_compose_memory", fake_compose)
    monkeypatch.setattr(
        backend, "_llm_build_index_label", lambda title, summary, content: "新版策略"
    )

    await backend.auto_retain("user-1", "新策略覆盖旧策略")

    updated_doc = backend._collection.docs[0]
    assert updated_doc["summary"] == "新版记忆存储策略"
    assert updated_doc["content"].startswith("新版方案：")


@pytest.mark.asyncio
async def test_retain_offloads_long_manual_memory_to_store(monkeypatch):
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()
    fake_store = FakeStore()
    long_content = "项目背景：" + ("需要把长文本记忆落到外部存储。" * 200)

    monkeypatch.setattr(settings, "NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS", 80)
    monkeypatch.setattr(settings, "NATIVE_MEMORY_STORE_NAMESPACE", "memories")

    async def fake_embed(text: str):
        return None

    async def fake_invalidate(user_id: str):
        return None

    async def fake_title(content: str):
        return "长文本约束"

    async def fake_summary(content: str):
        return "长文本需要外置存储"

    monkeypatch.setattr(backend, "_maybe_embed", fake_embed)
    monkeypatch.setattr(backend, "_invalidate_cache", fake_invalidate)
    monkeypatch.setattr(backend, "_llm_build_title", fake_title)
    monkeypatch.setattr(backend, "_llm_build_summary", fake_summary)
    monkeypatch.setattr(
        backend, "_llm_build_index_label", lambda title, summary, content: "长文本策略"
    )
    monkeypatch.setattr(backend, "_get_store", lambda: fake_store)

    result = await backend.retain("user-1", long_content, "project")

    assert result["success"] is True
    assert fake_store.put_calls, "expected long memory body to be written to store backend"
    stored_doc = backend._collection.inserted_docs[0]
    assert stored_doc["content_storage_mode"] == "store"
    assert stored_doc["content_store_key"]
    assert len(stored_doc["content"]) <= settings.NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS


@pytest.mark.asyncio
async def test_manual_retain_rejects_generic_low_value_memory():
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()

    result = await backend.retain("user-1", "我平时会写代码，也会看文档。", None)

    assert result["success"] is False


@pytest.mark.asyncio
async def test_retain_does_not_require_llm_index_label(monkeypatch):
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()

    async def fake_embed(text: str):
        return None

    async def fake_invalidate(user_id: str):
        return None

    async def fake_title(content: str):
        return "存储约束"

    async def fake_summary(content: str):
        return "长文本应外置到 StoreBackend"

    monkeypatch.setattr(backend, "_maybe_embed", fake_embed)
    monkeypatch.setattr(backend, "_invalidate_cache", fake_invalidate)
    monkeypatch.setattr(backend, "_llm_build_title", fake_title)
    monkeypatch.setattr(backend, "_llm_build_summary", fake_summary)

    def fail_index_label(*args, **kwargs):
        raise AssertionError("index label should be built without extra llm call")

    monkeypatch.setattr(backend, "_llm_build_index_label", fail_index_label)

    result = await backend.retain(
        "user-1",
        "项目要求：过长记忆正文统一外置到 StoreBackend，Mongo 只留摘要和引用。",
        "project",
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_recall_hydrates_store_backed_memory_text(monkeypatch):
    now = datetime.now(timezone.utc)
    full_text = "统一方案：长文本正文走 StoreBackend，Mongo 仅保留摘要、标题与引用。"
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection(
        [
            {
                "memory_id": "mem-3",
                "user_id": "user-1",
                "content": "统一方案：长文本正文走 StoreBack...",
                "content_storage_mode": "store",
                "content_store_key": "memory:mem-3",
                "summary": "统一长文本记忆存储策略",
                "title": "项目约束",
                "memory_type": "project",
                "source": "auto_retained",
                "created_at": now,
                "updated_at": now,
                "accessed_at": now,
                "access_count": 0,
            }
        ]
    )
    fake_store = FakeStore()
    fake_store.items[(("memories", "user-1", "content"), "memory:mem-3")] = {
        "text": full_text,
        "memory_id": "mem-3",
    }

    async def fake_update_access(memory_ids: list[str]):
        return None

    monkeypatch.setattr(backend, "_get_store", lambda: fake_store)
    monkeypatch.setattr(backend, "_update_access_stats", fake_update_access)

    result = await backend.recall("user-1", "项目约束", max_results=5)

    memory = result["memories"][0]
    assert memory["text"] == full_text
    assert memory["preview"] == "统一方案：长文本正文走 StoreBack..."
    assert memory["storage_mode"] == "store"


@pytest.mark.asyncio
async def test_recall_excludes_session_summaries_by_default(monkeypatch):
    now = datetime.now(timezone.utc)
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection(
        [
            {
                "memory_id": "mem-user",
                "user_id": "user-1",
                "content": "用户名叫杨洋，职业是程序员，主要负责维护 lambchat 开源项目。",
                "summary": "杨洋，程序员，维护lambchat开源项目。",
                "title": "LambChat Maintainer",
                "memory_type": "user",
                "source": "manual",
                "created_at": now,
                "updated_at": now,
                "accessed_at": now,
                "access_count": 0,
            },
            {
                "memory_id": "mem-session",
                "user_id": "user-1",
                "content": "[Session abc12345] 我是谁\n\n根据我的记忆，你是 YANG_YANG_LC。",
                "summary": "确认用户身份",
                "title": "Session abc12345",
                "memory_type": "reference",
                "source": "session_summary",
                "created_at": now,
                "updated_at": now,
                "accessed_at": now,
                "access_count": 0,
            },
        ]
    )

    async def fake_update_access(memory_ids: list[str]):
        return None

    monkeypatch.setattr(backend, "_update_access_stats", fake_update_access)

    result = await backend.recall("user-1", "user preferences project context", max_results=5)

    assert [memory["memory_id"] for memory in result["memories"]] == ["mem-user"]


@pytest.mark.asyncio
async def test_recall_always_ignores_session_summaries(monkeypatch):
    now = datetime.now(timezone.utc)
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection(
        [
            {
                "memory_id": "mem-session",
                "user_id": "user-1",
                "content": "[Session abc12345] 用户要求清空所有记忆，系统已执行。",
                "summary": "用户要求清空所有记忆",
                "title": "Session abc12345",
                "memory_type": "reference",
                "source": "session_summary",
                "created_at": now,
                "updated_at": now,
                "accessed_at": now,
                "access_count": 0,
            }
        ]
    )

    async def fake_update_access(memory_ids: list[str]):
        return None

    monkeypatch.setattr(backend, "_update_access_stats", fake_update_access)

    result = await backend.recall("user-1", "last session summary", max_results=5)

    assert result["memories"] == []


@pytest.mark.asyncio
async def test_store_session_summary_is_noop(monkeypatch):
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()

    async def fake_embed(text: str):
        return None

    async def fake_invalidate(user_id: str):
        return None

    monkeypatch.setattr(backend, "_maybe_embed", fake_embed)
    monkeypatch.setattr(backend, "_invalidate_cache", fake_invalidate)

    raw_summary = (
        "我是杨洋，是程序员，主要负责维护 lambchat 开源项目。\n\n"
        "你好杨洋！很高兴认识你。我已经记住了你的信息：\n"
        "- 姓名：杨洋\n- 职业：程序员\n- 主要项目：lambchat 开源项目（维护）\n\n"
        "有什么我可以帮你的吗？"
    )

    await backend.store_session_summary("user-1", "abcd1234-ffff", raw_summary)

    assert backend._collection.inserted_docs == []


@pytest.mark.asyncio
async def test_retain_llm_index_label_fallback(monkeypatch):
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()

    async def fake_embed(text: str):
        return None

    async def fake_invalidate(user_id: str):
        return None

    async def fake_title(content: str):
        return "长文本约束"

    async def fake_summary(content: str):
        return "长文本需要外置存储"

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("llm index label should not be called on write path")

    monkeypatch.setattr(backend, "_maybe_embed", fake_embed)
    monkeypatch.setattr(backend, "_invalidate_cache", fake_invalidate)
    monkeypatch.setattr(backend, "_llm_build_title", fake_title)
    monkeypatch.setattr(backend, "_llm_build_summary", fake_summary)
    monkeypatch.setattr(backend, "_llm_build_index_label", fail_if_called)

    result = await backend.retain(
        "user-1",
        "项目约束：过长记忆正文统一外置到 StoreBackend，Mongo 只留摘要和引用。",
        "project",
    )

    assert result["success"] is True
    assert backend._collection.inserted_docs[0]["index_label"]


def test_native_memory_store_related_defaults_exist():
    assert settings.NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS > 0
    assert settings.NATIVE_MEMORY_STORE_NAMESPACE
    assert settings.NATIVE_MEMORY_APPEND_MAX_DETAILS > 0


@pytest.mark.asyncio
async def test_build_memory_index_prefers_index_label():
    now = datetime.now(timezone.utc)
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection(
        [
            {
                "memory_id": "mem-4",
                "user_id": "user-1",
                "title": "一个很长的原标题",
                "index_label": "长记忆策略",
                "summary": "统一长文本记忆存储策略",
                "memory_type": "project",
                "updated_at": now,
            }
        ]
    )

    index_text = await backend.build_memory_index("user-1")

    assert "长记忆策略" in index_text
    assert "一个很长的原标题" not in index_text


@pytest.mark.asyncio
async def test_build_memory_index_ignores_session_summaries():
    now = datetime.now(timezone.utc)
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection(
        [
            {
                "memory_id": "mem-session",
                "user_id": "user-1",
                "title": "Session deadbeef",
                "index_label": "Session deadbeef",
                "summary": "旧会话摘要",
                "memory_type": "reference",
                "source": "session_summary",
                "updated_at": now,
            },
            {
                "memory_id": "mem-user",
                "user_id": "user-1",
                "title": "LambChat Maintainer",
                "index_label": "长记忆策略",
                "summary": "杨洋，程序员，维护lambchat开源项目。",
                "memory_type": "user",
                "source": "manual",
                "updated_at": now,
            },
        ]
    )

    index_text = await backend.build_memory_index("user-1")

    assert "长记忆策略" in index_text
    assert "Session deadbeef" not in index_text


def test_native_memory_guide_explains_memory_index_usage():
    assert "Each line is only a hint, not the full memory" in NATIVE_MEMORY_GUIDE
    assert "use `memory_recall` with the title or topic" in NATIVE_MEMORY_GUIDE
    assert "Session summaries are context bridges" not in NATIVE_MEMORY_GUIDE


@pytest.mark.asyncio
async def test_auto_retain_conversation_does_not_store_session_summary(monkeypatch):
    calls: list[tuple[str, ...]] = []

    class FakeBackend:
        async def auto_retain(self, user_id: str, conversation_summary: str, context: str | None):
            calls.append(("auto_retain", user_id, conversation_summary, context or ""))

        async def store_session_summary(self, user_id: str, session_id: str, summary: str):
            calls.append(("store_session_summary", user_id, session_id, summary))

    monkeypatch.setattr("src.infra.memory.tools._backend", FakeBackend())

    await auto_retain_conversation(
        "user-1",
        "用户是杨洋，负责维护 lambchat 开源项目。",
        context="conversation_turn",
        session_id="sess-123",
    )

    assert calls == [
        ("auto_retain", "user-1", "用户是杨洋，负责维护 lambchat 开源项目。", "conversation_turn")
    ]


@pytest.mark.asyncio
async def test_initialize_prunes_legacy_session_summary_records(monkeypatch):
    now = datetime.now(timezone.utc)
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection(
        [
            {
                "memory_id": "mem-session",
                "user_id": "user-1",
                "source": "session_summary",
                "updated_at": now,
            },
            {
                "memory_id": "mem-user",
                "user_id": "user-1",
                "source": "manual",
                "updated_at": now,
            },
        ]
    )

    monkeypatch.setattr(backend, "_ensure_collection", lambda: None)

    async def fake_create_indexes():
        return None

    monkeypatch.setattr(backend, "_create_indexes", fake_create_indexes)
    monkeypatch.setattr(backend, "_setup_embedding_fn", lambda: None)

    await backend.initialize()

    assert [doc["memory_id"] for doc in backend._collection.docs] == ["mem-user"]


@pytest.mark.asyncio
async def test_llm_extract_prompt_allows_stable_identity_memory(monkeypatch):
    backend = NativeMemoryBackend()
    captured: dict[str, object] = {}

    class FakeModel:
        async def ainvoke(self, messages):
            captured["messages"] = messages
            captured["system"] = messages[0].content
            return AIMessage(content="[]")

    monkeypatch.setattr(backend, "_get_memory_model", lambda: FakeModel())

    result = await backend._llm_extract_memories(
        "user-1", "我是杨洋，是一名程序员，主要维护 lambchat 开源项目。"
    )

    assert result == []
    assert len(captured["messages"]) == 1
    assert "SPECIAL CASE:" in captured["system"]
    assert "If the user explicitly states their name and a stable role" in captured["system"]
    assert "you may store it as a user memory" in captured["system"]
    assert "name + role is allowed" in captured["system"]


def test_format_conversation_for_extraction_adds_role_labels():
    backend = NativeMemoryBackend()

    formatted = backend._format_conversation_for_extraction(
        "我是杨洋，是一名程序员\n\n你好，杨洋！很高兴认识你。\n我已经记住了你的身份信息。"
    )

    assert "User: 我是杨洋，是一名程序员" in formatted
    assert "Assistant: 你好，杨洋！很高兴认识你。\n我已经记住了你的身份信息。" in formatted


@pytest.mark.asyncio
async def test_llm_extract_prompt_explains_user_and_assistant_roles(monkeypatch):
    backend = NativeMemoryBackend()
    captured: dict[str, str] = {}

    class FakeModel:
        async def ainvoke(self, messages):
            captured["system"] = messages[0].content
            return AIMessage(content="[]")

    monkeypatch.setattr(backend, "_get_memory_model", lambda: FakeModel())

    await backend._llm_extract_memories(
        "user-1",
        "我是杨洋，是一名程序员\n\n你好，杨洋！很高兴认识你。\n我已经记住了你的身份信息。",
    )

    assert "Prefer facts stated by the user." in captured["system"]
    assert "Assistant messages are usually acknowledgments" in captured["system"]
    assert "Conversation (role-labeled):" in captured["system"]
    assert "User: 我是杨洋，是一名程序员" in captured["system"]


@pytest.mark.asyncio
async def test_llm_extract_prompt_requires_output_language_to_match_input(monkeypatch):
    backend = NativeMemoryBackend()
    captured: dict[str, str] = {}

    class FakeModel:
        async def ainvoke(self, messages):
            captured["system"] = messages[0].content
            return AIMessage(content="[]")

    monkeypatch.setattr(backend, "_get_memory_model", lambda: FakeModel())

    await backend._llm_extract_memories(
        "user-1",
        "User: 我是杨洋，是一名程序员, 目前维护lambchat开源项目",
    )

    assert "LANGUAGE:" in captured["system"]
    assert "Use the same language as the source conversation" in captured["system"]
    assert "Do not translate Chinese inputs into English" in captured["system"]


@pytest.mark.asyncio
async def test_llm_extract_uses_single_system_message_for_offline_task(monkeypatch):
    backend = NativeMemoryBackend()
    captured: dict[str, object] = {}

    class FakeModel:
        async def ainvoke(self, messages):
            captured["messages"] = messages
            return AIMessage(content="[]")

    monkeypatch.setattr(backend, "_get_memory_model", lambda: FakeModel())

    await backend._llm_extract_memories(
        "user-1",
        "User: 我是杨洋，是一名程序员, 目前维护lambchat开源项目",
    )

    messages = captured["messages"]
    assert len(messages) == 1
    assert messages[0].type == "system"


@pytest.mark.asyncio
async def test_llm_extract_rewrites_summary_and_title_to_match_input_language(monkeypatch):
    backend = NativeMemoryBackend()

    class FakeModel:
        async def ainvoke(self, messages):
            return AIMessage(
                content=(
                    '[{"content":"我是杨洋，是一名程序员, 目前长期维护lambchat开源项目并负责核心功能开发",'
                    '"type":"user",'
                    '"summary":"User is Yang Yang, a programmer maintaining LambChat",'
                    '"title":"User Identity: Yang Yang"}]'
                )
            )

    async def fake_summary(content: str):
        return "杨洋，程序员，维护lambchat项目"

    async def fake_title(content: str):
        return "杨洋身份"

    monkeypatch.setattr(backend, "_get_memory_model", lambda: FakeModel())
    monkeypatch.setattr(backend, "_llm_build_summary", fake_summary)
    monkeypatch.setattr(backend, "_llm_build_title", fake_title)

    memories = await backend._llm_extract_memories(
        "user-1",
        "User: 我是杨洋，是一名程序员, 目前长期维护lambchat开源项目并负责核心功能开发",
    )

    assert memories[0]["summary"] == "杨洋，程序员，维护lambchat项目"
    assert memories[0]["title"] == "杨洋身份"


@pytest.mark.asyncio
async def test_manual_retain_does_not_call_llm_for_title_or_summary(monkeypatch):
    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()

    async def fail_title(content: str):
        raise AssertionError("manual retain should not call _llm_build_title")

    async def fail_summary(content: str):
        raise AssertionError("manual retain should not call _llm_build_summary")

    async def fake_maybe_embed(text: str):
        return None

    async def fake_invalidate(user_id: str):
        return None

    monkeypatch.setattr(backend, "_llm_build_title", fail_title)
    monkeypatch.setattr(backend, "_llm_build_summary", fail_summary)
    monkeypatch.setattr(backend, "_maybe_embed", fake_maybe_embed)
    monkeypatch.setattr(backend, "_invalidate_cache", fake_invalidate)

    result = await backend.retain(
        "user-1",
        "用户要求这个项目的 memory tool 不要再触发额外 LLM 请求，并保持行为可预测。",
        "project_constraint",
    )

    assert result["success"] is True
    stored = backend._collection.inserted_docs[0]
    assert stored["summary"]
    assert stored["title"]
