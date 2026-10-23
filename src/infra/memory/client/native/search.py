"""Search helpers for the native memory backend."""

from __future__ import annotations

import asyncio
import heapq
import re
from datetime import datetime
from typing import Any, Optional

import httpx

from src.infra.async_utils import run_blocking_io
from src.infra.llm.quota import is_quota_error, unpriced_usage
from src.infra.logging import get_logger
from src.infra.memory.client.native.content import (
    batch_get_memory_contents,
    hydrate_formatted_memory,
    sanitize_memory_text,
)
from src.infra.memory.client.native.models import (
    STOPWORDS,
    char_ngrams,
    has_cjk,
)
from src.infra.session.conversation_history import ConversationHistoryService
from src.infra.utils.datetime import ensure_utc, utc_now
from src.kernel.config import settings
from src.kernel.schemas.conversation_history import ConversationSourceRef

NATIVE_MEMORY_RECALL_MAX_RESULTS = 20
NATIVE_MEMORY_RECALL_QUERY_MAX_CHARS = 2_000
_VECTOR_SCOPE_OVERFETCH_FACTOR = 4
_VECTOR_MAX_CANDIDATES = 100
logger = get_logger(__name__)


def _clip_recall_query(query: str) -> str:
    normalized = str(query or "").strip()
    if len(normalized) <= NATIVE_MEMORY_RECALL_QUERY_MAX_CHARS:
        return normalized
    return normalized[:NATIVE_MEMORY_RECALL_QUERY_MAX_CHARS].rstrip()


def build_context_clause(context_filter: str) -> dict[str, Any]:
    """context 家族前缀子句：'project' 命中 project/project_status/project_constraint…

    记忆库的 context 是细粒度自由值，而工具文档只向模型暴露家族名（project/
    user/feedback/reference）；精确匹配会让一次家族猜测漏掉该族全部记忆
    （生产 6650ea0e：context='project' 只剩 2/50 条可命中）。
    """
    return {"$regex": f"^{re.escape(context_filter.strip())}"}


def build_scope_clause(project_id: Optional[str]) -> dict[str, Any]:
    """scope 硬过滤子句：归属边界先于相关性。

    - 无项目会话：只见 user/reference（含 legacy 无 scope 文档）
    - 项目会话：user/reference + 本项目 project 记忆；其他项目一律不可见
    """
    visible = {"$in": [None, "user", "reference"]}
    if project_id:
        return {
            "$or": [
                {"scope": visible},
                {"scope": "project", "project_id": project_id},
            ]
        }
    return {"scope": visible}


async def _hydrate_memories_limited(
    backend, memories: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not memories:
        return []

    items = await batch_get_memory_contents(backend, memories)
    results: list[dict[str, Any] | None] = [None] * len(memories)
    next_index = 0
    lock = asyncio.Lock()
    worker_count = min(
        max(1, int(getattr(settings, "NATIVE_MEMORY_HYDRATE_CONCURRENCY", 4) or 1)),
        len(memories),
    )

    async def _worker() -> None:
        nonlocal next_index
        while True:
            async with lock:
                if next_index >= len(memories):
                    return
                index = next_index
                next_index += 1
            if items is None:
                results[index] = await hydrate_formatted_memory(backend, memories[index])
            else:
                results[index] = await hydrate_formatted_memory(
                    backend, memories[index], item=items[index]
                )

    await asyncio.gather(*(_worker() for _ in range(worker_count)))
    return [memory for memory in results if memory is not None]


def build_keyword_clauses(query: str) -> list[dict[str, Any]]:
    normalized = query.strip()
    terms: list[str] = []

    if has_cjk(normalized):
        compact = re.sub(r"\s+", "", normalized)
        seen: set[str] = set()
        for n in (3, 2):
            for i in range(max(len(compact) - n + 1, 0)):
                term = compact[i : i + n]
                if len(term) < 2 or term in seen:
                    continue
                if all(ch in "的是在了和有" for ch in term):
                    continue
                seen.add(term)
                terms.append(term)
                if len(terms) >= 5:
                    break
            if len(terms) >= 5:
                break
    else:
        terms = [w for w in normalized.lower().split() if len(w) >= 2 and w not in STOPWORDS][:5]

    clauses: list[dict[str, Any]] = []
    for term in terms:
        escaped = re.escape(term)
        clauses.append({"content": {"$regex": escaped, "$options": "i"}})
        clauses.append({"summary": {"$regex": escaped, "$options": "i"}})
        clauses.append({"title": {"$regex": escaped, "$options": "i"}})
        clauses.append({"tags": {"$regex": escaped, "$options": "i"}})
    return clauses


def format_memory(doc: dict, score: float, now: datetime | None = None) -> dict:
    current_time = now or utc_now()
    staleness_days = (current_time - ensure_utc(doc["updated_at"])).days
    staleness_days_cfg = getattr(settings, "NATIVE_MEMORY_STALENESS_DAYS", 30)

    result: dict[str, Any] = {
        "memory_id": doc["memory_id"],
        "user_id": doc.get("user_id"),
        "text": sanitize_memory_text(doc["content"]),
        "preview": sanitize_memory_text(doc.get("content", "")),
        "summary": sanitize_memory_text(doc["summary"]),
        "title": sanitize_memory_text(doc.get("title", "")),
        "tags": [sanitize_memory_text(tag) for tag in (doc.get("tags") or [])],
        "type": doc["memory_type"],
        "scope": doc.get("scope") or "user",
        "project_id": doc.get("project_id"),
        "context": doc.get("context"),
        "source": doc.get("source", "manual"),
        "storage_mode": doc.get("content_storage_mode", "inline"),
        "content_store_key": doc.get("content_store_key"),
        "source_refs": doc.get("source_refs") or [],
        "created_at": doc["created_at"].isoformat()
        if isinstance(doc["created_at"], datetime)
        else str(doc["created_at"]),
        "updated_at": doc["updated_at"].isoformat()
        if isinstance(doc["updated_at"], datetime)
        else str(doc["updated_at"]),
        "score": score,
    }
    if staleness_days > staleness_days_cfg:
        result["staleness_warning"] = (
            f"This memory is {staleness_days} days old and may be outdated"
        )
    return result


def prioritize_sources(memories: list[dict]) -> list[dict]:
    source_order = {
        "manual": 0,
        "auto_retained": 1,
        "consolidated": 2,
        "session_summary": 99,
    }
    # 同 source 同分时当前项目上下文优先于用户级泛化记忆
    scope_order = {
        "project": 0,
        "user": 1,
        "reference": 1,
    }

    def ranking_key(memory: dict) -> tuple[float, int, int, int, float]:
        context = str(memory.get("context") or "")
        # Ownership is filtered before ranking; metadata only breaks relevance ties.
        lesson_rank = 0 if context.startswith("feedback") else 1
        updated_at = memory.get("updated_at")
        try:
            if isinstance(updated_at, datetime):
                updated_timestamp = updated_at.timestamp()
            else:
                updated_timestamp = datetime.fromisoformat(str(updated_at)).timestamp()
        except (TypeError, ValueError, OverflowError):
            updated_timestamp = 0.0
        return (
            -float(memory.get("score", 0.0) or 0.0),
            scope_order.get(str(memory.get("scope") or "user"), 1),
            lesson_rank,
            source_order.get(str(memory.get("source", "")), 50),
            -updated_timestamp,
        )

    return sorted(memories, key=ranking_key)


def is_context_overview_query(query: str) -> bool:
    lowered = query.strip().lower()
    overview_markers = (
        "user preferences",
        "project context",
        "context overview",
        "what should i know",
        "memory overview",
        "relevant memories",
        # Keep overview fallback usable for the locales supported by the UI.
        "记忆概览",
        "记忆总览",
        "用户偏好",
        "项目上下文",
        "相关记忆",
        "我需要知道什么",
        "メモリ概要",
        "ユーザー設定",
        "プロジェクトのコンテキスト",
        "関連する記憶",
        "메모리 개요",
        "사용자 선호",
        "프로젝트 컨텍스트",
        "관련 기억",
        "обзор памяти",
        "предпочтения пользователя",
        "контекст проекта",
        "релевантные воспоминания",
    )
    return any(marker in lowered for marker in overview_markers)


async def recent_context_fallback(
    collection,
    user_id: str,
    limit: int,
    memory_types: Optional[list[str]],
    context_filter: Optional[str] = None,
    project_id: Optional[str] = None,
) -> list[dict]:
    base: dict[str, Any] = {"user_id": user_id, "source": {"$ne": "session_summary"}}
    if memory_types:
        base["memory_type"] = {"$in": memory_types}
    if context_filter:
        base["context"] = build_context_clause(context_filter)
    base.update(build_scope_clause(project_id))
    cursor = (
        collection.find(
            base,
            {
                "memory_id": 1,
                "user_id": 1,
                "content": 1,
                "summary": 1,
                "title": 1,
                "memory_type": 1,
                "source": 1,
                "tags": 1,
                "scope": 1,
                "project_id": 1,
                "context": 1,
                "content_storage_mode": 1,
                "content_store_key": 1,
                "created_at": 1,
                "updated_at": 1,
                "source_refs": 1,
            },
        )
        .sort("updated_at", -1)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    # This is a recency-based overview fallback, not a semantic match. Give
    # selected documents a neutral passing score so the normal relevance gate
    # does not erase the overview that explicitly requested them.
    return [format_memory(doc, 1.0) for doc in docs]


async def text_search(
    collection,
    logger,
    user_id: str,
    query: str,
    limit: int,
    memory_types: Optional[list[str]],
    context_filter: Optional[str] = None,
    project_id: Optional[str] = None,
) -> list[dict]:
    base: dict[str, Any] = {"user_id": user_id, "source": {"$ne": "session_summary"}}
    if memory_types:
        base["memory_type"] = {"$in": memory_types}
    if context_filter:
        base["context"] = build_context_clause(context_filter)
    base.update(build_scope_clause(project_id))
    base["$text"] = {"$search": query}

    try:
        cursor = (
            collection.find(base, {"score": {"$meta": "textScore"}})
            .sort([("score", {"$meta": "textScore"})])
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
    except Exception:
        logger.debug("[NativeMemory] Text search failed, falling back to keyword match")
        docs = await keyword_fallback(
            collection, user_id, query, limit, memory_types, context_filter, project_id
        )
    else:
        if not docs:
            docs = await keyword_fallback(
                collection, user_id, query, limit, memory_types, context_filter, project_id
            )

    return [
        format_memory(
            doc,
            max(min(_memory_score(doc), 1.0), _keyword_match_score(query, doc)),
        )
        for doc in docs
    ]


async def keyword_fallback(
    collection,
    user_id: str,
    query: str,
    limit: int,
    memory_types: Optional[list[str]],
    context_filter: Optional[str] = None,
    project_id: Optional[str] = None,
) -> list[dict]:
    clauses = build_keyword_clauses(query)
    if not clauses:
        return []

    base: dict[str, Any] = {
        "user_id": user_id,
        "source": {"$ne": "session_summary"},
        "$or": clauses,
    }
    if memory_types:
        base["memory_type"] = {"$in": memory_types}
    if context_filter:
        base["context"] = build_context_clause(context_filter)
    scope_clause = build_scope_clause(project_id)
    if "$or" in scope_clause:
        base["$and"] = [scope_clause]
    else:
        base.update(scope_clause)

    _projection = {
        "memory_id": 1,
        "user_id": 1,
        "content": 1,
        "summary": 1,
        "title": 1,
        "memory_type": 1,
        "source": 1,
        "tags": 1,
        "scope": 1,
        "project_id": 1,
        "context": 1,
        "content_storage_mode": 1,
        "content_store_key": 1,
        "created_at": 1,
        "updated_at": 1,
        "source_refs": 1,
    }
    try:
        cursor = collection.find(base, _projection)
    except TypeError:
        cursor = collection.find(base)
    cursor = cursor.sort("updated_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    for doc in docs:
        doc["score"] = _keyword_match_score(query, doc)
    return docs


async def vector_search(
    backend,
    user_id: str,
    query: str,
    limit: int,
    memory_types: Optional[list[str]],
    context_filter: Optional[str] = None,
    project_id: Optional[str] = None,
) -> list[dict]:
    base: dict[str, Any] = {
        "user_id": user_id,
        "source": {"$ne": "session_summary"},
        "embedding": {"$exists": True, "$ne": None},
    }
    if memory_types:
        base["memory_type"] = {"$in": memory_types}
    if context_filter:
        base["context"] = build_context_clause(context_filter)
    base.update(build_scope_clause(project_id))

    # Qdrant 专用索引层（启用时优先；None=未启用/故障 → 走下方既有链路）
    from src.infra.memory.client.native.vector_store import index_search, vector_backend_enabled

    memory_ids: Optional[list[str]] = None
    if vector_backend_enabled():
        try:
            # Read IDs, not vectors; scope payloads in an older index are not authoritative.
            visible = await backend._collection.find(base, {"memory_id": 1, "_id": 0}).to_list(
                length=None
            )
            memory_ids = [doc["memory_id"] for doc in visible]
        except Exception:
            pass  # Keep the existing hydration/fallback path when the prefilter is unavailable.
        if memory_ids == []:
            return []

    query_vec = await backend._maybe_embed(query)
    if not query_vec:
        return []

    # 家族前缀 → 具体值列表：Qdrant payload 只存具体 context，MatchAny 下推
    context_values: Optional[list[str]] = None
    context_prefetch_failed = False
    if context_filter and memory_ids is None:
        try:
            distinct_contexts = await backend._collection.distinct(
                "context",
                {"user_id": user_id, "context": build_context_clause(context_filter)},
            )
            context_values = sorted({c for c in distinct_contexts if c})
            if not context_values:
                return []  # distinct 成功且家族确实为空：权威空结果
        except Exception:
            # 瞬时故障 ≠ 空家族：跳过 Qdrant 预过滤（context_values=None 会把
            # 过滤语义丢掉），改走下方 Mongo 链路的家族正则子句
            context_values = None
            context_prefetch_failed = True

    qdrant_hits = None
    if not context_prefetch_failed:
        # Authoritative IDs avoid filling the ANN window with other projects.
        ann_limit = min(
            max(
                limit
                * (_VECTOR_SCOPE_OVERFETCH_FACTOR if project_id and memory_ids is None else 1),
                limit,
            ),
            _VECTOR_MAX_CANDIDATES,
        )
        qdrant_hits = await index_search(
            vector=query_vec,
            user_id=user_id,
            limit=ann_limit,
            memory_types=memory_types,
            context_values=context_values,
            memory_ids=memory_ids,
        )
    if qdrant_hits:
        order = {h.memory_id: h.score for h in qdrant_hits}
        hydration_query: dict[str, Any] = {
            "user_id": user_id,
            "memory_id": {"$in": list(order)},
            "source": {"$ne": "session_summary"},
            "_vector_pending": {"$exists": False},
        }
        if memory_types:
            hydration_query["memory_type"] = {"$in": memory_types}
        if context_filter:
            hydration_query["context"] = build_context_clause(context_filter)
        hydration_query.update(build_scope_clause(project_id))
        cursor = backend._collection.find(hydration_query, {"embedding": 0})
        docs = await cursor.to_list(length=ann_limit)
        if len(docs) >= limit:
            docs.sort(key=lambda d: -order.get(d.get("memory_id"), 0.0))
            regular = [
                format_memory(doc, order.get(doc.get("memory_id"), 1.0)) for doc in docs[:limit]
            ]
            pending = await _mongo_cosine_search(
                backend, {**base, "_vector_pending": {"$exists": True}}, query_vec, limit
            )
            changed = await backend._collection.find(
                {
                    "user_id": user_id,
                    "memory_id": {"$in": [row["memory_id"] for row in regular]},
                    "_vector_pending": {"$exists": True},
                },
                {"memory_id": 1},
            ).to_list(length=len(regular))
            changed_ids = {row["memory_id"] for row in changed}
            merged = {
                row["memory_id"]: row for row in regular if row["memory_id"] not in changed_ids
            }
            merged.update({row["memory_id"]: row for row in pending})
            return sorted(merged.values(), key=lambda row: -row["score"])[:limit]
        # Mongo is authoritative: empty/partial index views, orphan points and
        # rejected scopes must not hide visible candidates beyond the ANN window.

    try:
        if await backend._collection.find_one(
            {**base, "_vector_pending": {"$exists": True}}, {"_id": 1}
        ):
            return await _mongo_cosine_search(backend, base, query_vec, limit)
        ann_limit = min(
            max(
                limit * (_VECTOR_SCOPE_OVERFETCH_FACTOR if project_id else 1),
                limit,
            ),
            _VECTOR_MAX_CANDIDATES,
        )
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "native_mem_vector_idx",
                    "path": "embedding",
                    "queryVector": query_vec,
                    "numCandidates": ann_limit * 5,
                    "limit": ann_limit,
                }
            },
            {"$match": base},
        ]
        cursor = await backend._collection.aggregate(pipeline)
        docs = await cursor.to_list(length=ann_limit)
        if docs:
            return [format_memory(doc, doc.get("score", 1.0)) for doc in docs[:limit]]
        # The Atlas stage can spend its candidate budget on vectors that the
        # post-filter rejects (especially when scope is not pushed down). Let
        # the bounded Python cosine scan fill visible results instead of
        # treating the filtered stage as an authoritative empty answer.
    except Exception:
        pass

    backend._logger.debug(
        "[NativeMemory] Atlas $vectorSearch unavailable, using Python cosine fallback"
    )
    return await _mongo_cosine_search(backend, base, query_vec, limit)


async def _mongo_cosine_search(
    backend, base: dict[str, Any], query_vec: list[float], limit: int
) -> list[dict]:
    # Scan vectors in bounded batches; recency must not hide an older relevant fact.
    cursor = backend._collection.find(base, {"memory_id": 1, "embedding": 1}).sort("updated_at", -1)
    if callable(getattr(cursor, "batch_size", None)):
        cursor = cursor.batch_size(256)

    async def vector_docs():
        if hasattr(cursor, "__aiter__"):
            async for doc in cursor:
                yield doc
        else:
            for doc in await cursor.to_list(length=None):
                yield doc

    best: list[tuple[float, str]] = []
    batch = []
    async for doc in vector_docs():
        batch.append(doc)
        if len(batch) == 256:
            scores = await run_blocking_io(_score_vector_batch, batch, query_vec)
            best = heapq.nlargest(limit, [*best, *scores], key=lambda item: item[0])
            batch = []
    if batch:
        scores = await run_blocking_io(_score_vector_batch, batch, query_vec)
        best = heapq.nlargest(limit, [*best, *scores], key=lambda item: item[0])
    if not best:
        return []
    scores_by_id = {mid: score for score, mid in best}
    docs = await backend._collection.find(
        {**base, "memory_id": {"$in": list(scores_by_id)}},
        {"embedding": 0},
    ).to_list(length=limit)
    docs_by_id = {doc["memory_id"]: doc for doc in docs}
    return [format_memory(docs_by_id[mid], score) for score, mid in best if mid in docs_by_id]


def _score_vector_batch(docs: list[dict], query: list[float]) -> list[tuple[float, str]]:
    # NumPy is provided by the existing qdrant-client dependency, including Mongo-only installs.
    import numpy as np

    valid = [
        doc
        for doc in docs
        if isinstance(doc.get("embedding"), list) and len(doc["embedding"]) == len(query)
    ]
    if not valid:
        return []
    try:
        vector = np.asarray(query, dtype=np.float32)
        query_norm = np.linalg.norm(vector)
    except (TypeError, ValueError):
        return []
    if not np.isfinite(query_norm) or query_norm <= 0:
        return []
    try:
        matrix = np.asarray([doc["embedding"] for doc in valid], dtype=np.float32)
    except (TypeError, ValueError):
        if len(valid) == 1:
            return []
        # A malformed row must not discard its valid neighbours.
        return [item for doc in valid for item in _score_vector_batch([doc], query)]
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        denominators = np.linalg.norm(matrix, axis=1) * query_norm
        scores = np.divide(
            matrix @ vector,
            denominators,
            out=np.full(len(valid), np.nan, dtype=np.float32),
            where=denominators > 0,
        )
    return [
        (float(np.clip(score, -1.0, 1.0)), doc["memory_id"])
        for doc, score in zip(valid, scores, strict=True)
        if np.isfinite(score)
    ]


def _query_terms(query: str) -> set[str]:
    normalized = query.strip().lower()
    if not normalized:
        return set()
    if has_cjk(normalized):
        return char_ngrams(normalized, 2) | char_ngrams(normalized, 3)
    return {w for w in re.findall(r"\w+", normalized) if len(w) >= 2 and w not in STOPWORDS}


def _field_overlap_score(query_terms: set[str], text: str) -> float:
    if not query_terms or not text.strip():
        return 0.0
    lowered = text.lower()
    if has_cjk(lowered):
        field_terms = char_ngrams(lowered, 2) | char_ngrams(lowered, 3)
    else:
        field_terms = {w for w in re.findall(r"\w+", lowered) if len(w) >= 2 and w not in STOPWORDS}
    if not field_terms:
        return 0.0
    overlap = len(query_terms & field_terms)
    coverage = overlap / max(len(query_terms), 1)
    density = overlap / max(len(field_terms), 1)
    # Query coverage is the gate: matching one frequent word in a six-word
    # query must not look relevant merely because the candidate field is short.
    return coverage * (0.7 + density * 0.3)


def _keyword_match_score(query: str, doc: dict[str, Any]) -> float:
    """Score a Mongo regex fallback using the strongest matching field.

    Mongo's ``$text`` metadata score is unavailable in the regex fallback. A
    bounded lexical score keeps exact tag/title matches useful while ensuring
    a single common word cannot pass a multi-term query's relevance threshold.
    """
    query_terms = _query_terms(query)
    if not query_terms:
        return 0.0
    raw_tags = doc.get("tags") or []
    tags_text = (
        " ".join(str(tag) for tag in raw_tags) if isinstance(raw_tags, list) else str(raw_tags)
    )
    return max(
        (
            _field_overlap_score(query_terms, str(doc.get("title", ""))),
            _field_overlap_score(query_terms, str(doc.get("summary", ""))),
            _field_overlap_score(query_terms, str(doc.get("content", ""))),
            _field_overlap_score(query_terms, tags_text),
        ),
        default=0.0,
    )


def local_rerank(query: str, candidates: list[dict], max_results: int) -> list[dict]:
    query_terms = _query_terms(query)

    def score(candidate: dict) -> tuple[float, float, float, float, float]:
        title_score = _field_overlap_score(query_terms, str(candidate.get("title", "")))
        summary_score = _field_overlap_score(query_terms, str(candidate.get("summary", "")))
        text_score = _field_overlap_score(query_terms, str(candidate.get("text", "")))
        raw_tags = candidate.get("tags") or []
        tags_text = (
            " ".join(str(tag) for tag in raw_tags) if isinstance(raw_tags, list) else str(raw_tags)
        )
        tags_score = _field_overlap_score(query_terms, tags_text)
        base_score = float(candidate.get("score", 0.0) or 0.0)
        blended = (
            base_score
            + tags_score * 1.0
            + title_score * 0.8
            + summary_score * 0.6
            + text_score * 0.3
        )
        return (
            blended,
            tags_score,
            title_score,
            summary_score,
            text_score,
        )

    ranked = sorted(candidates, key=score, reverse=True)
    return ranked[:max_results]


async def rerank_candidates(query: str, candidates: list[dict], max_results: int) -> list[dict]:
    rerank_model = getattr(settings, "NATIVE_MEMORY_RERANK_MODEL", "") or ""
    api_base = getattr(settings, "NATIVE_MEMORY_RERANK_API_BASE", "") or ""
    api_key = getattr(settings, "NATIVE_MEMORY_RERANK_API_KEY", "") or ""

    if not rerank_model or not api_base or not api_key or len(candidates) <= 1:
        return local_rerank(query, candidates, max_results)

    documents = [
        "\n".join(
            part
            for part in (
                str(candidate.get("title", "")).strip(),
                "Tags: " + ", ".join(str(tag) for tag in (candidate.get("tags") or [])),
                str(candidate.get("summary", "")).strip(),
                str(candidate.get("text", "")).strip(),
            )
            if part
        )
        for candidate in candidates
    ]

    try:
        async with httpx.AsyncClient(
            base_url=api_base.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(15.0),
        ) as client:
            async with unpriced_usage():
                response = await client.post(
                    "/v1/rerank",
                    json={
                        "model": rerank_model,
                        "query": query,
                        "documents": documents,
                        "top_n": max_results,
                    },
                )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        if is_quota_error(exc):
            raise
        return local_rerank(query, candidates, max_results)

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return local_rerank(query, candidates, max_results)

    ranked: list[dict] = []
    seen: set[int] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(candidates) or idx in seen:
            continue
        candidate = dict(candidates[idx])
        if "relevance_score" in item:
            candidate["score"] = float(item["relevance_score"])
        ranked.append(candidate)
        seen.add(idx)

    return ranked[:max_results] if ranked else local_rerank(query, candidates, max_results)


def _memory_score(memory: dict) -> float:
    try:
        return float(memory.get("score", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _recall_score(memory: dict) -> float:
    # Search backends may omit scores for an already-ranked text hit. Preserve
    # the historical pass-through behavior while handling malformed values.
    return 1.0 if "score" not in memory else _memory_score(memory)


def rrf_merge(
    text_results: list[dict], vector_results: list[dict], max_results: int, k: int = 60
) -> list[dict]:
    scores: dict[str, dict] = {}

    for rank, item in enumerate(text_results):
        mid = item["memory_id"]
        if mid not in scores:
            scores[mid] = {"data": item, "rrf_score": 0.0}
        scores[mid]["rrf_score"] += 1.0 / (k + rank + 1)

    for rank, item in enumerate(vector_results):
        mid = item["memory_id"]
        if mid not in scores:
            scores[mid] = {"data": item, "rrf_score": 0.0}
        elif _memory_score(item) > _memory_score(scores[mid]["data"]):
            # 同一记忆双路命中时保留高分字典：文本 keyword 兜底命中 score=0，
            # 若任其覆盖向量相似度，会被下游 min_score 阈值整体滤除
            scores[mid]["data"] = item
        scores[mid]["rrf_score"] += 1.0 / (k + rank + 1)

    merged = sorted(scores.values(), key=lambda x: x["rrf_score"], reverse=True)
    return [entry["data"] for entry in merged[:max_results]]


async def validate_memory_source_refs(
    user_id: str, memories: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Reauthorize recalled conversation pointers without dropping the memory."""
    normalized_by_memory: list[list[ConversationSourceRef]] = []
    all_refs: list[ConversationSourceRef] = []
    for memory in memories:
        normalized: list[ConversationSourceRef] = []
        for raw_ref in memory.get("source_refs") or []:
            try:
                ref = (
                    raw_ref
                    if isinstance(raw_ref, ConversationSourceRef)
                    else ConversationSourceRef.model_validate(raw_ref)
                )
            except Exception:
                continue
            normalized.append(ref)
            all_refs.append(ref)
        normalized_by_memory.append(normalized)

    if not all_refs:
        return [{**memory, "source_refs": []} for memory in memories]

    try:
        allowed_refs = await ConversationHistoryService().validate_source_refs(
            user_id, all_refs, limit=len(all_refs)
        )
    except Exception as exc:
        logger.warning(
            "[NativeMemory] Recalled source reference validation failed: %s",
            type(exc).__name__,
        )
        allowed_refs = []
    allowed_pairs = {(ref.session_id, ref.run_id) for ref in allowed_refs}

    validated: list[dict[str, Any]] = []
    for memory, refs in zip(memories, normalized_by_memory, strict=True):
        validated.append(
            {
                **memory,
                "source_refs": [
                    ref.model_dump()
                    for ref in refs
                    if (ref.session_id, ref.run_id) in allowed_pairs
                ],
            }
        )
    return validated


async def recall_memories(
    backend,
    user_id: str,
    query: str,
    max_results: int = 5,
    memory_types: Optional[list[str]] = None,
    touch_access: bool = True,
    enable_rerank: bool = True,
    context_filter: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict[str, Any]:
    max_results = max(1, min(int(max_results or 1), NATIVE_MEMORY_RECALL_MAX_RESULTS))
    query = _clip_recall_query(query)
    text_coro = text_search(
        backend._collection,
        backend._logger,
        user_id,
        query,
        max_results * 2,
        memory_types,
        context_filter,
        project_id,
    )

    if backend._embedding_fn:
        text_results, vector_results = await asyncio.gather(
            text_coro,
            vector_search(
                backend, user_id, query, max_results * 2, memory_types, context_filter, project_id
            ),
        )
    else:
        text_results = await text_coro
        vector_results = []

    memories = rrf_merge(text_results, vector_results, max_results * 2)
    # Rerank the full pool before filtering so remaining candidates can fill top-N.
    if enable_rerank and memories and len(memories) > 1:
        memories = await rerank_candidates(query, memories, len(memories))
    min_score = getattr(settings, "NATIVE_MEMORY_RECALL_MIN_SCORE", 0.3)
    if min_score > 0:
        memories = [m for m in memories if _recall_score(m) >= min_score]

    if not memories and is_context_overview_query(query):
        # An overview requests recent context, not a semantic match. Retrieve
        # it after the relevance gate so reranking cannot erase the fallback.
        # Keep enough candidates for scope/context priority even at max_results=1.
        overview_limit = max(max_results * 2, 10)
        memories = await recent_context_fallback(
            backend._collection, user_id, overview_limit, memory_types, context_filter, project_id
        )
        memories = prioritize_sources(memories)
    # Hybrid fusion and reranking already order normal hits. Their backend
    # scores use different scales and cannot be sorted together again.

    if memories:
        memories = memories[:max_results]
        memories = await _hydrate_memories_limited(backend, memories)
        memories = await validate_memory_source_refs(user_id, memories)

        if touch_access:
            await backend._update_access_stats([m["memory_id"] for m in memories], user_id)

    return {
        "success": True,
        "query": query,
        "memories": memories,
        "search_mode": "hybrid" if backend._embedding_fn else "text",
    }
