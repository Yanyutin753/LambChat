"""自进化记忆——夜间离线反思管线。

从差评（feedback rating=down）与失败 run 的对话中蒸馏"教训"，
存为 context=feedback_rule 的 feedback 记忆（source=self_evolved）。
借鉴护栏（Codex/Claude Code）：离线写入、严格 schema、脱敏、排除规则压过
指令、纠正与正反馈同记、每晚安额、LLM 失败静默跳过。
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.kernel.config import settings

logger = logging.getLogger(__name__)

SIGNAL_WINDOW_HOURS = 24
SIGNAL_RUNS_CAP = 5
POSITIVE_SAMPLE_RATE = 0.2
EXCHANGE_CLIP_CHARS = 1500

REFLECT_SYSTEM_PROMPT = """You are an offline reflection engine distilling behavioral lessons \
from a conversation that went poorly (or was validated by the user).
You see the exchange and the outcome. Extract AT MOST ONE reusable lesson.

Call memory_retain with:
- content: three lines, exactly this shape:
  rule: <imperative sentence, <=80 chars>
  why: <what went wrong or was validated, <=60 chars>
  how_to_apply: <when/condition to apply, <=60 chars>
- context: "feedback_rule"
- title: the rule, <=25 chars
- summary: the rule, <=80 chars
- tags: 2-4 short keywords

HARD EXCLUSIONS (never extract even if useful-looking):
- Anything derivable from code, git history, or docs.
- One-off task details, greetings, small talk.
- Secrets or sensitive values — redact as <redacted>.
- Generic LLM advice not tied to this exchange.

If a listed existing lesson already covers it, call memory_retain with \
existing_memory_id set to that lesson's memory id (update instead of duplicate).
If nothing worth extracting, call no tool."""


@dataclass(frozen=True)
class SignalRun:
    run_id: str
    session_id: str
    kind: str  # "down" | "failed" | "up"
    comment: Optional[str] = None


def _get_feedback_collection():
    from src.infra.storage.mongodb import get_mongo_client

    return get_mongo_client()[settings.MONGODB_DB]["feedback"]


def _get_traces_collection():
    from src.infra.storage.mongodb import get_mongo_client

    return get_mongo_client()[settings.MONGODB_DB]["traces"]


async def collect_signal_runs(
    user_id: str, *, hours: int = SIGNAL_WINDOW_HOURS, cap: int = SIGNAL_RUNS_CAP
) -> list[SignalRun]:
    """差评 run（带评论优先）+ 失败 run，窗口内去重截断。"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    signals: list[SignalRun] = []
    try:
        fb_docs = (
            await _get_feedback_collection()
            .find(
                {
                    "user_id": user_id,
                    "rating": "down",
                    "created_at": {"$gte": cutoff},
                    "evolution_processed": {"$ne": True},
                }
            )
            .sort("created_at", -1)
            .limit(cap)
            .to_list(length=cap)
        )
        for d in fb_docs:
            signals.append(
                SignalRun(
                    run_id=str(d.get("run_id") or ""),
                    session_id=str(d.get("session_id") or ""),
                    kind="down",
                    comment=d.get("comment"),
                )
            )
    except Exception as e:
        logger.debug("[MemoryEvolution] feedback scan failed: %s", e)

    try:
        tr_docs = (
            await _get_traces_collection()
            .find({"user_id": user_id, "status": "failed", "started_at": {"$gte": cutoff}})
            .sort("started_at", -1)
            .limit(cap)
            .to_list(length=cap)
        )
        for d in tr_docs:
            signals.append(
                SignalRun(
                    run_id=str(d.get("run_id") or ""),
                    session_id=str(d.get("session_id") or ""),
                    kind="failed",
                )
            )
    except Exception as e:
        logger.debug("[MemoryEvolution] trace scan failed: %s", e)

    seen: set[str] = set()
    deduped: list[SignalRun] = []
    for s in signals:
        if s.run_id and s.run_id not in seen:
            seen.add(s.run_id)
            deduped.append(s)
    # 差评优先（信息量大），带评论的更优先
    deduped.sort(
        key=lambda s: 0 if (s.kind == "down" and s.comment) else 1 if s.kind == "down" else 2
    )
    return deduped[:cap]


async def collect_positive_runs(
    user_id: str, *, hours: int = SIGNAL_WINDOW_HOURS, cap: int = 3
) -> list[SignalRun]:
    """好评 run（防漂移采样：验证过的做法也记）。"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        docs = (
            await _get_feedback_collection()
            .find({"user_id": user_id, "rating": "up", "created_at": {"$gte": cutoff}})
            .sort("created_at", -1)
            .limit(cap)
            .to_list(length=cap)
        )
        return [
            SignalRun(
                run_id=str(d.get("run_id") or ""),
                session_id=str(d.get("session_id") or ""),
                kind="up",
            )
            for d in docs
        ]
    except Exception as e:
        logger.debug("[MemoryEvolution] positive scan failed: %s", e)
        return []


async def _mark_signal_processed(signal: SignalRun) -> None:
    """down 信号处理一次后打标，防下轮调度重复反思同一 run。"""
    if signal.kind != "down":
        return
    try:
        await _get_feedback_collection().update_one(
            {"user_id": {"$exists": True}, "run_id": signal.run_id, "rating": "down"},
            {"$set": {"evolution_processed": True}},
        )
    except Exception as e:
        logger.debug("[MemoryEvolution] mark processed failed: %s", e)


def _should_sample_positive(rng: Optional[random.Random] = None) -> bool:
    return (rng or random).random() < POSITIVE_SAMPLE_RATE


async def _load_exchange(run_id: str) -> tuple[str, str]:
    """从 trace（inline events 或 chunks）取该 run 的用户消息与最终助手回复。"""
    from src.infra.storage.mongodb import get_mongo_client

    client = get_mongo_client()
    db = client[settings.MONGODB_DB]
    events: list[dict[str, Any]] = []
    trace = await db.traces.find_one({"run_id": run_id}, {"events": 1})
    if trace:
        events = trace.get("events") or []
    if not events:
        chunks = (
            await db.trace_event_chunks.find({"run_id": run_id}, {"events": 1})
            .sort("chunk_index", 1)
            .to_list(length=20)
        )
        for c in chunks:
            events.extend(c.get("events") or [])

    user_msg = ""
    assistant_msg = ""
    for ev in events:
        et = ev.get("event_type") or ev.get("type")
        data = ev.get("data") or {}
        if et == "user:message" and data.get("content"):
            user_msg = str(data["content"])
        elif et == "message:chunk" and data.get("content"):
            assistant_msg = str(data["content"])  # 取最后一个 chunk 的合并文本
    return user_msg[:EXCHANGE_CLIP_CHARS], assistant_msg[:EXCHANGE_CLIP_CHARS]


async def reflect_on_run(backend, user_id: str, signal: SignalRun) -> dict:
    """对单个信号 run 跑反思 LLM，产出教训则 retain。失败静默跳过。"""
    try:
        user_msg, assistant_msg = await _load_exchange(signal.run_id)
    except Exception as e:
        logger.debug("[MemoryEvolution] exchange load failed for %s: %s", signal.run_id, e)
        return {"stored": 0}

    if not user_msg and not signal.comment:
        return {"stored": 0}

    outcome = {
        "down": f"User rated this run DOWN. Comment: {signal.comment or '(none)'}",
        "failed": "This run FAILED (assistant errored or never completed).",
        "up": "User rated this run UP (validated practice — record what worked, anti-drift).",
    }[signal.kind]

    # 相似既有教训喂给 LLM 做去重
    try:
        similar = await backend.recall(
            user_id,
            user_msg or signal.comment or "",
            max_results=3,
            touch_access=False,
            enable_rerank=False,
            context_filter="feedback_rule",
        )
        existing_text = "\n".join(
            f"- id={m.get('memory_id')} {str(m.get('summary') or m.get('title'))[:60]}"
            for m in (similar.get("memories") or [])
        )
    except Exception:
        existing_text = ""

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from src.infra.llm.retry import ainvoke_with_retry
        from src.infra.memory.client.native.content import maybe_await
        from src.infra.memory.tools import memory_retain

        model = (await maybe_await(backend._get_memory_model())).bind_tools([memory_retain])
        response = await ainvoke_with_retry(
            model,
            [
                SystemMessage(content=REFLECT_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"User message:\n{user_msg or '(unavailable)'}\n\n"
                        f"Assistant reply (tail):\n{assistant_msg or '(unavailable/failed)'}\n\n"
                        f"Outcome: {outcome}\n\n"
                        f"Existing lessons:\n{existing_text or '(none)'}"
                    )
                ),
            ],
            operation="memory-evolution-reflect",
        )
    except Exception as e:
        logger.info("[MemoryEvolution] reflect LLM failed for run %s: %s", signal.run_id, e)
        return {"stored": 0}

    stored = 0
    for tool_call in getattr(response, "tool_calls", None) or []:
        if tool_call.get("name") != "memory_retain":
            continue
        args = tool_call.get("args") or {}
        content = str(args.get("content") or "").strip()
        if not content:
            continue
        result = await backend.retain(
            user_id,
            content,
            context=args.get("context") or "feedback_rule",
            title=args.get("title"),
            summary=args.get("summary"),
            tags=args.get("tags"),
            existing_memory_id=args.get("existing_memory_id"),
        )
        if result.get("success") and result.get("memory_id") and backend._collection is not None:
            try:
                await backend._collection.update_one(
                    {"user_id": user_id, "memory_id": result["memory_id"]},
                    {"$set": {"source": "self_evolved"}},
                )
            except Exception as e:
                logger.debug("[MemoryEvolution] source tagging failed: %s", e)
        if result.get("success"):
            stored += 1
    return {"stored": stored}


async def evolve_user(backend, user_id: str, *, max_per_night: Optional[int] = None) -> dict:
    """单用户一晚的进化：差评/失败优先，正反馈采样，晚安额。"""
    from src.infra.memory.user_pref import user_memory_enabled

    if not await user_memory_enabled(user_id):
        return {"stored": 0}
    limit = int(
        max_per_night or getattr(settings, "NATIVE_MEMORY_SELF_EVOLVE_MAX_PER_NIGHT", 3) or 3
    )
    signals = await collect_signal_runs(user_id)
    stored = 0
    for sig in signals:
        if stored >= limit:
            break
        r = await reflect_on_run(backend, user_id, sig)
        stored += int(r.get("stored") or 0)
        await _mark_signal_processed(sig)

    if stored < limit and _should_sample_positive():
        for sig in await collect_positive_runs(user_id):
            if stored >= limit:
                break
            r = await reflect_on_run(backend, user_id, sig)
            stored += int(r.get("stored") or 0)
    if stored:
        logger.info("[MemoryEvolution] user %s evolved %d lesson(s)", user_id, stored)
    return {"stored": stored}
