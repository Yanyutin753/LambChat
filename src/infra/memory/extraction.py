"""Codex 式记忆提取流水线（Phase 1: 会话 → 原始记忆）。

移植自 openai/codex `codex-rs/memories`（README + write crate）的两阶段设计：

- Phase 1（本模块）：对「空闲会话」做全量转录提取——用户连发多轮的汇报类会话，
  其完整事实（供应商/价格/决策）在最后一轮交换里根本看不全，这正是旧「每轮
  评估器」漏记的根因（生产 6650ea0e：皮蛋供应商会话零沉淀）。语义对照 codex：
  - 空闲窗口（idle long enough）内不提取仍在进行的会话；
  - 认领租约 + 失败退避（lease/backoff），多副本不重跑；
  - 结构化输出 raw_memory + rollout_summary + rollout_slug；
  - 无信号 no-op（succeeded_no_output）是合法且被偏好的结局；
  - 密钥脱敏后进 prompt。
- Phase 2 沿用既有 MemoryCompactionAgent（合并/去重/冷却/全局锁），提取成功后
  通过 maybe_compact_after_write 挂接，与 codex 的全局合并阶段对应。
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.infra.llm.quota import bind_quota_user, is_quota_error
from src.infra.logging import get_logger
from src.infra.memory.extraction_content import (
    _clip_transcript as _clip_transcript,
)
from src.infra.memory.extraction_content import (
    load_session_transcript,
    parse_stage_one_output,
    redact_secrets,
    render_stage_one_input,
    response_text,
)
from src.infra.memory.forgetting import source_watermark
from src.infra.utils.datetime import ensure_utc, utc_now
from src.kernel.config import settings

logger = get_logger(__name__)

EXTRACTION_JOBS_COLLECTION = "memory_extraction_jobs"
TEMPLATE_PATH = Path(__file__).parent / "templates" / "memories" / "stage_one_system.md"

_LEASE_SECONDS = 900
# 终态：不再重试；claimed 带租约；failed 带 next_retry_at 退避。
# exhausted = attempts 耗尽；二者在会话出现新活动时可重开（见 _maybe_reopen_job）。
_TERMINAL_STATUSES = ("succeeded", "succeeded_no_output")
_REOPENABLE_STATUSES = _TERMINAL_STATUSES + ("exhausted",)


@dataclass
class ExtractionOutcome:
    status: str
    memory_id: str | None = None
    error: str | None = None
    # 确定性失败（解析/截断类）不重试：重试只会重复烧配额，直接判 exhausted
    retryable: bool = True
    memory_ids: tuple[str, ...] = ()
    input_fingerprint: str | None = None
    resume_state: dict[str, Any] | None = None
    retained_count: int | None = None


# 解析失败是模型输出形态问题，重试同样输入不会变好
_NON_RETRYABLE_ERRORS = {"unparseable_output", "output_truncated"}


def extraction_settings() -> dict[str, Any]:
    """提取流水线配置（集中读取，便于测试覆写）。"""
    return {
        "enabled": bool(getattr(settings, "MEMORY_EXTRACTION_ENABLED", True)),
        "idle_seconds": int(getattr(settings, "MEMORY_EXTRACTION_IDLE_SECONDS", 1800)),
        "max_age_days": int(getattr(settings, "MEMORY_EXTRACTION_MAX_AGE_DAYS", 30)),
        "max_sessions_per_pass": int(
            getattr(settings, "MEMORY_EXTRACTION_MAX_SESSIONS_PER_PASS", 3)
        ),
        "max_attempts": int(getattr(settings, "MEMORY_EXTRACTION_MAX_ATTEMPTS", 3)),
        "transcript_max_chars": int(
            getattr(settings, "MEMORY_EXTRACTION_TRANSCRIPT_MAX_CHARS", 24_000)
        ),
    }


def build_extraction_candidate_query(
    user_id: str, *, now: datetime, idle_seconds: int, max_age_days: int
) -> dict[str, Any]:
    """空闲会话候选查询（codex startup claim rules 的 Mongo 化）。

    - 活跃会话 + 归属用户
    - updated_at 在 [now - max_age_days, now - idle_seconds]：太新（可能仍在
      进行）与太旧（超出记忆窗口）都不提
    - 排除隐藏会话与定时任务会话（sch_ 前缀，非用户交互源）
    """
    return {
        "user_id": user_id,
        "is_active": True,
        "updated_at": {
            "$gte": now - timedelta(days=max_age_days),
            "$lt": now - timedelta(seconds=idle_seconds),
        },
        "metadata.hidden_from_conversation_list": {"$ne": True},
        "session_id": {"$not": {"$regex": "^sch_"}},
    }


async def find_candidate_sessions(
    db, user_id: str, *, limit: int, jobs_collection_name: str = "memory_extraction_jobs"
) -> list[dict[str, Any]]:
    cfg = extraction_settings()
    now = utc_now()
    # Exclude unavailable work before the limit; completed recent sessions must not hide older work.
    cursor = await db[settings.MONGODB_SESSIONS_COLLECTION].aggregate(
        [
            {
                "$match": build_extraction_candidate_query(
                    user_id,
                    now=now,
                    idle_seconds=cfg["idle_seconds"],
                    max_age_days=cfg["max_age_days"],
                )
            },
            {"$sort": {"updated_at": -1, "_id": -1}},
            {
                "$set": {
                    "_candidate_id": {
                        "$toString": {
                            "$cond": [{"$ifNull": ["$session_id", False]}, "$session_id", "$_id"]
                        }
                    }
                }
            },
            {
                "$lookup": {
                    "from": jobs_collection_name,
                    "localField": "_candidate_id",
                    "foreignField": "session_id",
                    "pipeline": [
                        {
                            "$project": {
                                "user_id": 1,
                                "status": 1,
                                "attempts": 1,
                                "extracted_updated_at": 1,
                                "updated_at": 1,
                                "lease_expires_at": 1,
                                "next_retry_at": 1,
                            }
                        }
                    ],
                    "as": "_candidate_jobs",
                }
            },
            {"$set": {"_candidate_job": {"$arrayElemAt": ["$_candidate_jobs", 0]}}},
            {
                "$match": {
                    "$or": [
                        {"_candidate_jobs": []},
                        {
                            "_candidate_job.user_id": user_id,
                            "$or": [
                                {
                                    "_candidate_job.status": {"$in": list(_REOPENABLE_STATUSES)},
                                    "$expr": {
                                        "$let": {
                                            "vars": {
                                                "extracted": {
                                                    "$cond": [
                                                        {
                                                            "$ifNull": [
                                                                "$_candidate_job.extracted_updated_at",
                                                                False,
                                                            ]
                                                        },
                                                        "$_candidate_job.extracted_updated_at",
                                                        "$_candidate_job.updated_at",
                                                    ]
                                                }
                                            },
                                            "in": {
                                                "$and": [
                                                    {"$eq": [{"$type": "$$extracted"}, "date"]},
                                                    {"$gt": ["$updated_at", "$$extracted"]},
                                                ]
                                            },
                                        }
                                    },
                                },
                                {
                                    "_candidate_job.status": {"$nin": list(_REOPENABLE_STATUSES)},
                                    "_candidate_job.attempts": {
                                        "$not": {"$gte": cfg["max_attempts"]}
                                    },
                                    "_candidate_job.next_retry_at": {"$not": {"$gt": now}},
                                    "$or": [
                                        {"_candidate_job.status": {"$ne": "claimed"}},
                                        {"_candidate_job.lease_expires_at": {"$not": {"$gt": now}}},
                                    ],
                                },
                            ],
                        },
                    ]
                }
            },
            {
                "$lookup": {
                    "from": settings.MONGODB_TRACES_COLLECTION,
                    "localField": "_candidate_id",
                    "foreignField": "session_id",
                    "pipeline": [
                        {"$match": {"user_id": user_id, "status": "running"}},
                        {"$limit": 1},
                        {"$project": {"_id": 1}},
                    ],
                    "as": "_running_traces",
                }
            },
            {"$match": {"_running_traces": []}},
            {"$limit": limit},
            {
                "$project": {
                    "session_id": 1,
                    "name": 1,
                    "updated_at": 1,
                    "metadata.agent_id": 1,
                    "metadata.project_id": 1,
                }
            },
        ]
    )
    docs = await cursor.to_list(length=limit)
    return [
        {**doc, "session_id": str(doc.get("session_id") or doc["_id"])}
        for doc in docs
        if doc.get("session_id") or doc.get("_id")
    ]


async def ensure_extraction_job_indexes(jobs_collection) -> None:
    """Create idempotent indexes required for multi-replica claiming."""
    await jobs_collection.create_index(
        [("session_id", 1)],
        name="memory_extraction_session_unique",
        unique=True,
    )
    await jobs_collection.create_index(
        [("user_id", 1), ("status", 1), ("next_retry_at", 1)],
        name="memory_extraction_retry_scan",
    )
    for field in ("memory_ids", "memory_id"):
        await jobs_collection.create_index(
            [("user_id", 1), (field, 1)],
            name=f"memory_extraction_{field}_source",
        )


async def _session_has_running_trace(db, session_id: str, user_id: str) -> bool:
    running = await db[settings.MONGODB_TRACES_COLLECTION].count_documents(
        {"session_id": session_id, "user_id": user_id, "status": "running"}
    )
    return int(running) > 0


async def claim_candidate_jobs(
    db,
    jobs_collection,
    user_id: str,
    *,
    limit: int,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Claim up to `limit` jobs, scanning past recent terminal sessions."""
    if limit <= 0:
        return []
    candidates = await find_candidate_sessions(
        db,
        user_id,
        limit=min(max(limit * 10, limit), 100),
        jobs_collection_name=getattr(jobs_collection, "name", "memory_extraction_jobs"),
    )
    claimed: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for session_doc in candidates:
        # 仍在跑的会话不认领：此刻提取会漏掉进行中的 run，且终态会把漏提内容锁死
        if await _session_has_running_trace(db, str(session_doc.get("session_id")), user_id):
            continue
        job = await claim_session_job(jobs_collection, session_doc, user_id)
        if job is None:
            continue
        claimed.append((session_doc, job))
        if len(claimed) >= limit:
            break
    return claimed


def _maybe_reopen_job(
    existing: dict[str, Any], session_doc: dict[str, Any], *, now: datetime, lease_expires: datetime
) -> bool:
    """终态/耗尽的 job 是否应因会话出现新活动而重开。

    候选查询已保证 session.updated_at 落在空闲窗口内（新活动也空闲了），
    这里只需比对上次提取记录的水位 extracted_updated_at。
    """
    session_updated = session_doc.get("updated_at")
    if not isinstance(session_updated, datetime):
        return False
    extracted_at = existing.get("extracted_updated_at") or existing.get("updated_at")
    if not isinstance(extracted_at, datetime):
        return False
    return session_updated > extracted_at


async def claim_session_job(
    jobs_collection, session_doc: dict[str, Any], user_id: str, *, now: datetime | None = None
) -> dict[str, Any] | None:
    """原子认领：无记录则插入 claimed；failed 且退避到期可重试；带租约防多副本并发。

    终态/耗尽但会话又有新（且已再次空闲的）活动的 job 原子重开，水位见
    run_extraction_pass 落库的 extracted_updated_at。
    返回认领后的 job 文档；不可认领返回 None。
    """
    now = now or utc_now()
    session_id = str(session_doc.get("session_id"))
    existing = await jobs_collection.find_one({"session_id": session_id})
    lease_expires = now + timedelta(seconds=_LEASE_SECONDS)

    if existing is None:
        job = {
            "session_id": session_id,
            "user_id": user_id,
            "status": "claimed",
            "attempts": 1,
            "lease_expires_at": lease_expires,
            "next_retry_at": None,
            "created_at": now,
            "updated_at": now,
        }
        try:
            await jobs_collection.insert_one(job)
        except DuplicateKeyError:
            return None  # 并发插入：另一副本已认领（unique index on session_id）
        return job

    if existing.get("user_id") != user_id:
        return None

    if existing.get("status") in _REOPENABLE_STATUSES:
        if not _maybe_reopen_job(existing, session_doc, now=now, lease_expires=lease_expires):
            return None
        return await jobs_collection.find_one_and_update(
            {
                "_id": existing["_id"],
                "user_id": user_id,
                # 只允许从同一终态原子迁移：并发重开只有一方成功
                "status": existing.get("status"),
            },
            {
                "$set": {
                    "status": "claimed",
                    "attempts": 1,
                    "lease_expires_at": lease_expires,
                    "next_retry_at": None,
                    "error": None,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
    attempts = int(existing.get("attempts") or 0)
    max_attempts = extraction_settings()["max_attempts"]
    if attempts >= max_attempts:
        return None
    next_retry_at = existing.get("next_retry_at")
    if isinstance(next_retry_at, datetime) and next_retry_at > now:
        return None
    lease = existing.get("lease_expires_at")
    if existing.get("status") == "claimed" and isinstance(lease, datetime) and lease > now:
        return None

    result = await jobs_collection.find_one_and_update(
        {
            "_id": existing["_id"],
            "user_id": user_id,
            # 条件写：租约/退避窗口内不得被并发抢占
            "$or": [
                {"lease_expires_at": {"$lte": now}},
                {"status": "failed"},
            ],
        },
        {
            "$set": {
                "status": "claimed",
                "lease_expires_at": lease_expires,
                "updated_at": now,
            },
            "$inc": {"attempts": 1},
        },
        return_document=ReturnDocument.AFTER,
    )
    return result


def load_stage_one_system_prompt() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


async def _get_extraction_model() -> Any:
    from src.infra.llm.client import LLMClient
    from src.infra.llm.models_service import resolve_model_reference

    model_id, model_value = await resolve_model_reference(
        getattr(settings, "NATIVE_MEMORY_MODEL", "")
    )
    model_kwargs: dict[str, Any] = {
        "model_id": model_id,
        "temperature": 0.1,
    }
    # 0 = 不限制（默认）：思考型模型的 thinking 块会先吃输出预算，固定小
    # 上限会把结构化 JSON 截断成必然解析失败；不传时用模型默认上限
    max_tokens = int(getattr(settings, "NATIVE_MEMORY_MAX_TOKENS", 0) or 0)
    if max_tokens > 0:
        model_kwargs["max_tokens"] = max_tokens
    if model_value:
        model_kwargs["model"] = model_value
    return await LLMClient.get_model(**model_kwargs)


def _fallback_index_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """索引字段兜底：模板要求模型直出，缺失时从 raw_memory 头部推导（避免二次
    LLM 调用；与旧 auto-retain 的 _fallback_enrich 同思路）。"""
    from src.infra.memory.client.native.summaries import _fallback_enrich

    enriched = _fallback_enrich(payload["raw_memory"])
    context = payload.get("context") or ""
    if context not in {"user", "feedback", "project", "reference"}:
        context = "project"
    return {
        "title": payload.get("title") or enriched["title"],
        "summary": payload.get("summary") or enriched["summary"],
        "tags": payload.get("tags") or enriched["tags"],
        "context": context,
    }


@bind_quota_user
async def extract_session_memory(
    backend,
    db,
    user_id: str,
    session_doc: dict[str, Any],
    *,
    previous_input_fingerprint: str | None = None,
    resume_state: dict[str, Any] | None = None,
    save_resume_state: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> ExtractionOutcome:
    """单个会话的 Phase 1 提取：转录 → LLM 结构化输出 → retain 落库。"""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    from src.infra.llm.retry import _is_output_limit_response, ainvoke_with_retry

    cfg = extraction_settings()
    session_id = str(session_doc.get("session_id"))
    watermark = await source_watermark(db, user_id, session_id)
    turns = await load_session_transcript(
        db,
        session_id,
        user_id,
        max_chars=cfg["transcript_max_chars"],
        **({"not_before": watermark} if watermark is not None else {}),
    )
    if not turns:
        if watermark is not None:
            return ExtractionOutcome("succeeded_no_output")
        # 会话在候选窗口内说明有消息；转录为空 = conversation_search 索引未就绪
        # 或数据异常。判 failed 走退避重试，不得终态 no-op 把漏提内容锁死。
        return ExtractionOutcome("failed", error="transcript_unavailable")

    metadata = session_doc.get("metadata") or {}
    agent_id = str(metadata.get("agent_id") or "")
    system_prompt = load_stage_one_system_prompt()
    user_prompt = render_stage_one_input(str(session_doc.get("name") or ""), agent_id, turns)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "user_id": user_id,
                "session_id": session_id,
                "system": system_prompt,
                "input": user_prompt,
                "run_ids": [turn.get("run_id") for turn in turns],
                "project_id": metadata.get("project_id"),
                "forgotten_before": watermark.isoformat() if watermark is not None else None,
                "model": getattr(settings, "NATIVE_MEMORY_MODEL", ""),
                "max_tokens": getattr(settings, "NATIVE_MEMORY_MAX_TOKENS", 0),
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    if fingerprint == previous_input_fingerprint:
        return ExtractionOutcome("succeeded_no_output", input_fingerprint=fingerprint)

    payload = None
    start_index = 0
    memory_ids: list[str] = []
    if resume_state and resume_state.get("input_fingerprint") == fingerprint:
        saved_payload = parse_stage_one_output(json.dumps(resume_state.get("payload")))
        saved_index = resume_state.get("next_index")
        saved_ids = resume_state.get("memory_ids")
        if (
            saved_payload
            and not saved_payload.get("noop")
            and type(saved_index) is int
            and 0 <= saved_index <= len(saved_payload.get("memories", [saved_payload]))
            and isinstance(saved_ids, list)
            and all(isinstance(mid, str) for mid in saved_ids)
        ):
            payload, start_index, memory_ids = saved_payload, saved_index, list(saved_ids)

    from src.infra.memory.extraction_gate import evaluate_extraction_gate

    if payload is None:
        gate = await evaluate_extraction_gate(
            session_id, str(session_doc.get("name") or ""), agent_id, turns
        )
        if gate is not None and gate.skip:
            return ExtractionOutcome("succeeded_no_output", input_fingerprint=fingerprint)
        try:
            model = await _get_extraction_model()
            response = await ainvoke_with_retry(
                model,
                [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)],
                operation="memory-extraction-phase1",
            )
            if isinstance(response, AIMessage) and _is_output_limit_response(response):
                logger.warning(
                    "[MemoryExtraction] output limited for session %s; retrying compact output once",
                    session_id,
                )
                response = await ainvoke_with_retry(
                    model,
                    [
                        SystemMessage(content=system_prompt),
                        HumanMessage(
                            content=user_prompt
                            + "\n\nOutput recovery: the previous response hit the output limit. "
                            "Return one complete compact JSON object. Shorten formatting, "
                            "rollout summaries and duplicate wording only. Preserve all "
                            "qualifying memories, distinct scopes/topics, exact facts, evidence "
                            "qualifications and the original quality and safety requirements. "
                            "Do not return a no-op merely to fit the output budget."
                        ),
                    ],
                    operation="memory-extraction-phase1-compact",
                )
                if isinstance(response, AIMessage) and _is_output_limit_response(response):
                    return ExtractionOutcome("failed", error="output_truncated", retryable=False)
        except Exception as exc:
            if is_quota_error(exc):
                raise
            logger.warning("[MemoryExtraction] LLM call failed for session %s: %s", session_id, exc)
            return ExtractionOutcome("failed", error=str(exc))
        payload = parse_stage_one_output(response_text(response))
    if payload is None:
        return ExtractionOutcome("failed", error="unparseable_output")
    if payload.get("noop"):
        return ExtractionOutcome("succeeded_no_output", input_fingerprint=fingerprint)

    payload["rollout_summary"] = redact_secrets(payload["rollout_summary"])
    memories = payload.get("memories", [payload])
    for memory in memories:
        for key in ("raw_memory", "title", "summary"):
            memory[key] = redact_secrets(memory.get(key) or "")
        memory["tags"] = [redact_secrets(tag) for tag in memory.get("tags", [])]
    state = {
        "input_fingerprint": fingerprint,
        "payload": payload,
        "memory_ids": memory_ids,
        "next_index": start_index,
    }
    # Persist paid output before writes, then checkpoint each committed item under the claim fence.
    if save_resume_state:
        await save_resume_state(state)

    async def check_write_claim() -> bool:
        if await source_watermark(db, user_id, session_id) != watermark:
            raise RuntimeError("memory_source_forgotten")
        if save_resume_state:
            await save_resume_state(state)
        return True

    source_refs = [
        {"session_id": session_id, "run_id": turn["run_id"]} for turn in turns if turn.get("run_id")
    ][-20:]
    # 项目归属继承源会话（metadata.project_id）：拿不到可靠归属时 retain 侧
    # 自动降级 user scope，不猜测
    session_project_id = str((metadata or {}).get("project_id") or "").strip() or None
    retained_count = 0
    for index, memory in enumerate(memories[start_index:], start=start_index):
        index_fields = _fallback_index_fields(memory)
        # 索引字段同样过脱敏：title/summary/tags 会进 memory index 常驻暴露
        index_fields = {
            **index_fields,
            "title": redact_secrets(index_fields["title"]),
            "summary": redact_secrets(index_fields["summary"]),
            "tags": [redact_secrets(t) for t in index_fields["tags"]],
        }
        from src.infra.memory.extraction_gate import log_context_second_opinion

        await log_context_second_opinion(session_id, index_fields, memory["raw_memory"])
        memory_scope = "user" if index_fields["context"] == "user" else None
        try:
            result = await backend.retain(
                user_id,
                redact_secrets(memory["raw_memory"]),
                context=index_fields["context"],
                title=index_fields["title"],
                summary=index_fields["summary"],
                tags=index_fields["tags"],
                source_refs=source_refs,
                scope=memory_scope,
                project_id=session_project_id if memory_scope is None else None,
                source="auto_retained",
                origin_session_id=session_id,
                write_guard=check_write_claim,
            )
        except Exception as exc:
            if is_quota_error(exc):
                raise
            # 只记异常类型：异常原文可能携带用户记忆内容（详细原因进 job.error）
            logger.warning(
                "[MemoryExtraction] retain failed for session %s: %s",
                session_id,
                type(exc).__name__,
            )
            return ExtractionOutcome(
                "failed",
                error=str(exc),
                memory_ids=tuple(memory_ids),
                resume_state=state,
                retained_count=retained_count,
            )
        if not result.get("success"):
            return ExtractionOutcome(
                "failed",
                error=str(result.get("error") or "retain_rejected"),
                retryable=result.get("retryable") is not False,
                memory_ids=tuple(memory_ids),
                resume_state=state,
                retained_count=retained_count,
            )
        memory_id = result.get("memory_id")
        if not result.get("unchanged"):
            retained_count += 1
        if memory_id and getattr(backend, "_collection", None) is not None:
            try:
                metadata_update = {"rollout_summary": payload["rollout_summary"][:4000]}
                await backend._collection.update_one(
                    {"user_id": user_id, "memory_id": memory_id},
                    {"$set": metadata_update},
                )
            except Exception as exc:
                # 记忆已落库：元数据是锦上添花，失败只降级告警，
                # 把 job 判失败会触发重试 → 重复 LLM + 潜在重复记忆
                logger.warning(
                    "[MemoryExtraction] metadata write failed (memory kept) for %s: %s",
                    session_id,
                    type(exc).__name__,
                )
        if memory_id:
            memory_ids.append(memory_id)
        state["next_index"] = index + 1
        if save_resume_state:
            await save_resume_state(state)
    return ExtractionOutcome(
        "succeeded",
        memory_id=memory_ids[0] if memory_ids else None,
        memory_ids=tuple(memory_ids),
        input_fingerprint=fingerprint,
        retained_count=retained_count,
    )


def _backoff_next_retry(attempts: int, *, now: datetime | None = None) -> datetime:
    now = now or utc_now()
    return now + timedelta(seconds=min(300, 60 * (2 ** max(0, attempts - 1))))


@bind_quota_user
async def run_extraction_pass(user_id: str, *, backend=None) -> dict[str, Any]:
    """一轮提取：认领 ≤N 个空闲会话逐个处理，更新 job 终态/退避。

    成功落库后挂接 Phase 2（compaction），对应 codex 的两阶段衔接。
    """
    from src.infra.storage.mongodb import get_mongo_client

    cfg = extraction_settings()
    if not cfg["enabled"]:
        return {"skipped": 1, "reason": "disabled"}

    from src.infra.memory.user_pref import user_memory_enabled

    if not await user_memory_enabled(user_id):
        return {"skipped": 1, "reason": "memory_disabled_for_user"}

    if backend is None:
        from src.infra.memory.tools import _get_backend

        backend = await _get_backend()
    if backend is None:
        return {"skipped": 1, "reason": "backend_unavailable"}

    from src.infra.memory.distributed import (
        check_auto_retain_daily_limit,
        record_auto_retain_usage,
    )

    # 配额按「成功 retain」计数（record_auto_retain_usage），peek 不消耗额度：
    # 空转 pass、模型 no-op、LLM 失败都不再占用每日上限
    if await check_auto_retain_daily_limit(user_id) == "exceeded":
        return {"skipped": 1, "reason": "daily_limit"}

    from src.infra.usage.quota import UsageQuota, user_budgets

    # Leave untouched jobs eligible after reset; mid-extraction denials remain terminal.
    try:
        budgets = await user_budgets(user_id)
        quota = await UsageQuota().snapshot(user_id, budgets)
    except Exception as exc:
        if is_quota_error(exc):
            return {"skipped": 1, "reason": exc.error_code.code}
        raise
    if any(quota[name]["blocked"] for name in ("five_hour", "weekly")):
        return {"skipped": 1, "reason": "usage_quota_exceeded"}

    client = get_mongo_client()
    db = client[settings.MONGODB_DB]
    jobs = db[EXTRACTION_JOBS_COLLECTION]
    await ensure_extraction_job_indexes(jobs)

    claimed_jobs = await claim_candidate_jobs(
        db,
        jobs,
        user_id,
        limit=cfg["max_sessions_per_pass"],
    )
    results = {"claimed": 0, "succeeded": 0, "succeeded_no_output": 0, "failed": 0}
    stored_memory = False
    quota_denied = False
    for session_doc, job in claimed_jobs:
        # 中途额度耗尽（其它 pass 抢先记满）即停：剩余 job 留给租约/下次扫描
        if await check_auto_retain_daily_limit(user_id) == "exceeded":
            logger.info("[MemoryExtraction] daily limit hit mid-pass for %s", user_id)
            break
        results["claimed"] += 1
        session_id = str(session_doc.get("session_id"))
        fence = {
            "_id": job["_id"],
            "status": "claimed",
            "attempts": int(job.get("attempts") or 0),
            "lease_expires_at": job.get("lease_expires_at"),
        }

        async def save_resume_state(state: dict[str, Any]) -> None:
            lease = fence["lease_expires_at"]
            if not isinstance(lease, datetime) or ensure_utc(lease) <= utc_now():
                raise RuntimeError("extraction_claim_expired")
            saved = await jobs.update_one(fence, {"$set": {"resume_state": state}})
            if not int(getattr(saved, "matched_count", 1) or 0):
                raise RuntimeError("extraction_claim_lost")

        try:
            outcome = await extract_session_memory(
                backend,
                db,
                user_id,
                session_doc,
                previous_input_fingerprint=job.get("input_fingerprint"),
                resume_state=job.get("resume_state"),
                save_resume_state=save_resume_state,
            )
        except Exception as exc:
            logger.warning("[MemoryExtraction] unexpected failure for %s: %s", session_id, exc)
            quota_denied = is_quota_error(exc)
            outcome = ExtractionOutcome("failed", error=str(exc), retryable=not quota_denied)
        now = utc_now()
        retained_count = outcome.retained_count
        if retained_count is None:
            retained_count = 1 if outcome.status == "succeeded" else 0

        async def account_retains() -> None:
            nonlocal stored_memory
            for _ in range(retained_count):
                await record_auto_retain_usage(user_id)
                stored_memory = True

        # fencing：终态写入校验认领时的 attempts + 租约时间戳；租约被其它副本
        # 抢占后陈旧 worker 的写不生效（attempts/lease 均已推进）
        watermark = {"extracted_updated_at": session_doc.get("updated_at")}
        if outcome.status == "failed":
            attempts = int(job.get("attempts") or 0)
            non_retryable = not outcome.retryable or outcome.error in _NON_RETRYABLE_ERRORS
            update: dict[str, Any] = {
                "$set": {
                    "status": "failed",
                    "error": outcome.error,
                    "updated_at": now,
                    "next_retry_at": _backoff_next_retry(attempts, now=now),
                    **watermark,
                    **({"memory_ids": list(outcome.memory_ids)} if outcome.memory_ids else {}),
                }
            }
            if attempts >= cfg["max_attempts"] or non_retryable:
                update["$set"]["status"] = "exhausted"
                update["$set"]["next_retry_at"] = None
            result = await jobs.update_one(fence, update)
            if not int(getattr(result, "matched_count", 1) or 0):
                logger.warning(
                    "[MemoryExtraction] stale claim for %s, skip failure write", session_id
                )
            else:
                await account_retains()
            results["failed"] += 1
            if quota_denied:
                break
            continue
        # 终态写清理退避残留；memory_id 仅在成功时更新（no-op 不得抹掉历史血缘）
        terminal_set: dict[str, Any] = {
            "status": outcome.status,
            "error": None,
            "next_retry_at": None,
            "updated_at": now,
            **watermark,
        }
        if outcome.input_fingerprint:
            terminal_set["input_fingerprint"] = outcome.input_fingerprint
        terminal_set["resume_state"] = None
        if outcome.status == "succeeded":
            terminal_set["memory_id"] = outcome.memory_id
            terminal_set["memory_ids"] = list(
                outcome.memory_ids or ((outcome.memory_id,) if outcome.memory_id else ())
            )
        result = await jobs.update_one(fence, {"$set": terminal_set})
        if not int(getattr(result, "matched_count", 1) or 0):
            logger.warning("[MemoryExtraction] stale claim for %s, skip terminal write", session_id)
            results["failed"] += 1
            continue
        await account_retains()
        results[outcome.status] += 1

    if stored_memory and not quota_denied:
        try:
            from src.infra.memory.compaction_agent import get_memory_compaction_agent

            await get_memory_compaction_agent().maybe_compact_after_write(backend, user_id)
        except Exception as exc:
            logger.warning("[MemoryExtraction] phase-2 compaction hook failed: %s", exc)

    logger.info("[MemoryExtraction] pass for user %s: %s", user_id, results)
    return results


_extraction_tasks: set[asyncio.Task] = set()
_extraction_inflight_users: set[str] = set()


async def stop_memory_extraction_tasks() -> None:
    """Cancel detached extraction passes during process shutdown."""
    tasks = list(_extraction_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _extraction_tasks.clear()
    _extraction_inflight_users.clear()


def schedule_memory_extraction(user_id: str) -> None:
    """Run 结束后的 best-effort kick：同用户在途去重；真正的节流由认领/租约/
    退避/每日限额保证（kick 频繁只会命中「无可认领会话」的快路径）。"""
    if not user_id:
        return
    if not extraction_settings()["enabled"]:
        return
    if user_id in _extraction_inflight_users:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _detached() -> None:
        from langsmith.run_helpers import tracing_context

        with tracing_context(parent=False):
            await run_extraction_pass(user_id)

    _extraction_inflight_users.add(user_id)
    # A pass may process older sessions; foreground callbacks and runtime must not follow it.
    task = loop.create_task(_detached(), context=contextvars.Context())
    _extraction_tasks.add(task)

    def _done(t: asyncio.Task) -> None:
        _extraction_tasks.discard(t)
        _extraction_inflight_users.discard(user_id)
        try:
            exc = t.exception()
            if exc:
                logger.warning("[MemoryExtraction] background pass failed: %s", exc)
        except asyncio.CancelledError:
            pass

    task.add_done_callback(_done)


def start_memory_extraction_agent() -> None:
    """注册定期提取任务（覆盖「用户再没回来」的空闲会话，对应 codex startup 扫描）。

    无条件注册：ENABLE_MEMORY 动态开启后由 enabled lambda 立即放行，
    无需重启进程补注册。
    """
    if not settings.ENABLE_MEMORY:
        logger.info("[MemoryExtraction] scheduler registered but idle until ENABLE_MEMORY=true")

    from src.infra.scheduler import ScheduledJob, get_runtime_scheduler

    def _interval() -> int:
        return int(getattr(settings, "MEMORY_EXTRACTION_INTERVAL_SECONDS", 900))

    get_runtime_scheduler().register_job(
        ScheduledJob.from_interval(
            id="memory.extraction",
            name="Memory extraction (Phase 1)",
            interval_seconds=_interval,
            enabled=lambda: (
                bool(settings.ENABLE_MEMORY)
                and bool(getattr(settings, "MEMORY_EXTRACTION_ENABLED", True))
            ),
            handler=run_scheduled_memory_extraction,
        )
    )


async def run_scheduled_memory_extraction() -> dict:
    """定期扫一轮活跃用户的空闲会话（认领语义保证与 per-run kick 不冲突）。

    每轮经 schedule_memory_extraction 派发：pass 任务纳入 _extraction_tasks，
    进程关闭时统一 drain，且同用户在途去重。
    """
    from src.infra.storage.mongodb import get_mongo_client

    if not extraction_settings()["enabled"]:
        return {"skipped": 1, "reason": "disabled"}
    client = get_mongo_client()
    db = client[settings.MONGODB_DB]
    now = utc_now()
    window = now - timedelta(days=extraction_settings()["max_age_days"])
    cursor = await db[settings.MONGODB_SESSIONS_COLLECTION].aggregate(
        [
            {
                "$match": {
                    "is_active": True,
                    "updated_at": {"$gte": window},
                    "metadata.hidden_from_conversation_list": {"$ne": True},
                    "session_id": {"$not": {"$regex": "^sch_"}},
                    "user_id": {"$exists": True, "$nin": [None, ""]},
                }
            },
            {"$group": {"_id": "$user_id", "latest": {"$max": "$updated_at"}}},
            {"$sort": {"latest": -1, "_id": 1}},
            {"$project": {"_id": 0, "user_id": "$_id"}},
        ]
    )
    user_ids: list[str] = []
    seen: set[str] = set()
    async for doc in cursor:
        uid = str(doc.get("user_id") or "")
        if uid and uid not in seen:
            seen.add(uid)
            user_ids.append(uid)

    max_users_per_round = 50
    if len(user_ids) > max_users_per_round:
        # Rotate a full batch each interval; busy accounts cannot occupy every round.
        interval = max(1, int(getattr(settings, "MEMORY_EXTRACTION_INTERVAL_SECONDS", 900)))
        start = (int(now.timestamp()) // interval * max_users_per_round) % len(user_ids)
        user_ids = user_ids[start:] + user_ids[:start]
    selected = user_ids[:max_users_per_round]

    for uid in selected:
        schedule_memory_extraction(uid)
    return {"users": len(selected), "dispatched": len(selected)}
