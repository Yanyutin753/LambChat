"""Legacy junk/duplicate memory cleanup (generic, dry-run by default).

设计对齐 codex 记忆系统的两条通用规则，不做任何写死的短语黑名单——
换一个用户、换一批垃圾同样适用：

1. 语义去重：同用户内 embedding 余弦（缺 embedding 时退化为摘要 char 2-gram
   Jaccard）≥ 阈值判近重复，保留最新一条，旧副本进清理清单。
2. durable 判定：用与写入端 Phase 1 提取器同一套「最小信号门控」rubric 让
   记忆模型逐条判断「该记忆是否陈述了至少一个可复用的持久事实」，无信号
   （自述无上下文/纯寒暄/只描述消息形态）判 JUNK，并给出理由供人工复核。

用法::

    uv run python scripts/cleanup_junk_memories.py                 # 仅语义去重，dry-run
    uv run python scripts/cleanup_junk_memories.py --with-llm      # 加做 LLM durable 审查
    uv run python scripts/cleanup_junk_memories.py --apply         # 执行删除（交互确认）
    uv run python scripts/cleanup_junk_memories.py --apply --yes   # 执行删除（免确认）
    uv run python scripts/cleanup_junk_memories.py --user <id>     # 限定用户
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

# Support the documented `uv run python scripts/...` invocation from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

DEFAULT_DUP_THRESHOLD = 0.8
WORD_DUP_THRESHOLD = 0.9
LLM_JUDGE_MAX_BATCH = 500

DURABILITY_JUDGE_PROMPT = """You are a memory cleanup reviewer using the same \
durability rubric as the memory writing agent.

Given one stored memory (title/summary/content), decide whether it states at \
least one durable, reusable fact about the user or their work: identity, \
preferences, decisions, business facts (suppliers, prices, dates, quantities), \
constraints, or lasting references.

Judge JUNK when the memory only describes the FORM of a message (what the user \
sent), carries no usable fact (bare question/acknowledgement/greeting with no \
context), or duplicates nothing more than common knowledge. Judge KEEP when any \
durable, reusable fact survives.

Reply with exactly one line, no prose:
KEEP - <short reason>
or
JUNK - <short reason>"""


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def word_similarity(a: str, b: str) -> float:
    """char 2-gram Jaccard（CJK 友好），与分类器同款度量。"""
    if not a or not b:
        return 0.0

    def grams(text: str) -> set[str]:
        compact = "".join(text.split())
        return {compact[i : i + 2] for i in range(max(len(compact) - 1, 0))}

    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def memory_similarity(doc_a: dict[str, Any], doc_b: dict[str, Any]) -> float:
    """优先 embedding 余弦；缺失时退化为摘要 Jaccard（近重复专用高阈值）。"""
    emb_a, emb_b = doc_a.get("embedding"), doc_b.get("embedding")
    if isinstance(emb_a, list) and isinstance(emb_b, list):
        return cosine_similarity(emb_a, emb_b)
    return word_similarity(str(doc_a.get("summary") or ""), str(doc_b.get("summary") or ""))


def _updated_sort_key(doc: dict[str, Any]) -> str:
    """updated_at 排序键：datetime（.isoformat() 含 'T'）与 ISO 字符串混存时，
    直接 str() 会因 'T' > ' ' 排错序——统一归一化到 isoformat 可比形式。"""
    value = doc.get("updated_at")
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def find_duplicate_memory_ids(
    docs: list[dict[str, Any]],
    *,
    dup_threshold: float = DEFAULT_DUP_THRESHOLD,
    word_threshold: float = WORD_DUP_THRESHOLD,
) -> list[str]:
    """同用户内近重复分组：保留 updated_at 最新的一条，其余进清理清单。

    O(n²) 仅在清理脚本一次性运行时使用；按用户分组后 n 是单用户记忆数。
    阈值按「成对」判定：两边都有 embedding 才用余弦档，否则（含混合对，
    实际度量退化为 Jaccard）一律用更严的 Jaccard 档，避免误删。
    """
    by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in docs:
        by_user[str(doc.get("user_id") or "")].append(doc)

    def _pair_threshold(doc: dict[str, Any], other: dict[str, Any]) -> float:
        both_embedded = isinstance(doc.get("embedding"), list) and isinstance(
            other.get("embedding"), list
        )
        return dup_threshold if both_embedded else word_threshold

    flagged: list[str] = []
    for user_docs in by_user.values():
        ordered = sorted(
            user_docs,
            key=_updated_sort_key,
            reverse=True,
        )  # 新 → 旧
        kept: list[dict[str, Any]] = []
        for doc in ordered:
            duplicate_of_kept = any(
                memory_similarity(doc, other) >= _pair_threshold(doc, other) for other in kept
            )
            if duplicate_of_kept:
                flagged.append(str(doc.get("memory_id")))
            else:
                kept.append(doc)
    return flagged


def parse_judge_reply(text: str) -> tuple[bool, str]:
    """解析 KEEP/JUNK 单行判定；无法解析时保守 KEEP。"""
    line = (text or "").strip().splitlines()[0].strip() if text and text.strip() else ""
    upper = line.upper()
    if upper.startswith("KEEP"):
        return True, line
    if upper.startswith("JUNK"):
        return False, line
    return True, "unparseable (kept by default)"


async def judge_memory_durability(model: Any, doc: dict[str, Any]) -> dict[str, Any]:
    """单条 durable 判定；异常时保守 KEEP（清理是删数据，宁可漏删不可误删）。"""
    from langchain_core.messages import HumanMessage, SystemMessage

    from src.infra.memory.extraction import response_text

    content = str(doc.get("content") or doc.get("summary") or "")[:4000]
    user_prompt = (
        f"title: {doc.get('title') or ''}\nsummary: {doc.get('summary') or ''}\ncontent: {content}"
    )
    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=DURABILITY_JUDGE_PROMPT),
                HumanMessage(content=user_prompt),
            ]
        )
        keep, reason = parse_judge_reply(response_text(response))
    except Exception as exc:
        # 只记异常类型：异常原文可能携带用户记忆内容
        logger.warning(
            "[MemoryCleanup] judge failed for %s: %s",
            doc.get("memory_id"),
            type(exc).__name__,
        )
        return {
            "memory_id": doc.get("memory_id"),
            "keep": True,
            "reason": f"error: {type(exc).__name__}",
        }
    return {"memory_id": doc.get("memory_id"), "keep": keep, "reason": reason}


async def _get_judge_model() -> Any:
    from src.infra.llm.client import LLMClient
    from src.infra.llm.models_service import resolve_model_reference

    model_id, model_value = await resolve_model_reference(
        getattr(settings, "NATIVE_MEMORY_MODEL", "")
    )
    model_kwargs: dict[str, Any] = {
        "model_id": model_id,
        "temperature": 0.0,
    }
    # 0 = 不限制（默认）：思考型模型 thinking 块会先吃预算，小上限会让
    # KEEP/JUNK 单行根本轮不到生成（保守 KEEP 掩盖了故障）
    max_tokens = int(getattr(settings, "NATIVE_MEMORY_MAX_TOKENS", 0) or 0)
    if max_tokens > 0:
        model_kwargs["max_tokens"] = max_tokens
    if model_value:
        model_kwargs["model"] = model_value
    return await LLMClient.get_model(**model_kwargs)


async def plan_cleanup(
    collection,
    *,
    user_id: Optional[str] = None,
    use_llm: bool = False,
    dup_threshold: float = DEFAULT_DUP_THRESHOLD,
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if user_id:
        query["user_id"] = user_id
    projection = {
        "memory_id": 1,
        "user_id": 1,
        "title": 1,
        "summary": 1,
        "content": 1,
        "source": 1,
        "context": 1,
        "updated_at": 1,
        "embedding": 1,
        # apply 需要按 doc 清理外部内容存储与向量索引
        "content_storage_mode": 1,
        "content_store_key": 1,
    }
    docs = await collection.find(query, projection).to_list(length=10_000)

    duplicate_ids = find_duplicate_memory_ids(docs, dup_threshold=dup_threshold)
    dup_set = set(duplicate_ids)

    judgments: list[dict[str, Any]] = []
    if use_llm:
        model = await _get_judge_model()
        to_judge = [d for d in docs if str(d.get("memory_id")) not in dup_set][:LLM_JUDGE_MAX_BATCH]
        for doc in to_judge:
            judgments.append(await judge_memory_durability(model, doc))

    junk_ids = [j["memory_id"] for j in judgments if not j["keep"]]
    return {
        "total": len(docs),
        # 报告脱敏：计划里只携带 memory_id，不携带标题等用户内容
        "duplicates": [{"memory_id": mid} for mid in duplicate_ids],
        "judgments": judgments,
        "junk_ids": junk_ids,
        "docs_by_id": {str(d.get("memory_id")): d for d in docs},
    }


async def apply_cleanup(collection, plan: dict[str, Any]) -> dict[str, int]:
    """执行删除，顺序对齐 NativeMemoryBackend.delete：Mongo（事实源）→ 外部
    内容存储 → 向量索引。外部内容单条失败不中断批次（统计失败数供跟进），
    遗留的向量点可由索引重建，遗留的外部内容是孤儿数据需人工清理。"""
    ids = [str(item["memory_id"]) for item in plan["duplicates"]] + list(plan["junk_ids"])
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {"deleted": 0}

    from src.infra.memory.client.native.content import delete_memory_content
    from src.infra.memory.client.native.vector_store import index_delete

    result = await collection.delete_many({"memory_id": {"$in": ids}})
    deleted = int(getattr(result, "deleted_count", 0) or 0)

    content_shim = SimpleNamespace(_store=None)  # delete_memory_content 按需自建 store
    content_deleted = 0
    content_delete_failed = 0
    for memory_id in ids:
        doc = plan["docs_by_id"].get(memory_id) or {}
        user_id = str(doc.get("user_id") or "")
        if doc.get("content_storage_mode") == "store" and doc.get("content_store_key"):
            try:
                await delete_memory_content(content_shim, user_id, doc["content_store_key"])
                content_deleted += 1
            except Exception as exc:
                # 只记异常类型：异常原文可能携带用户记忆内容
                logger.warning(
                    "[MemoryCleanup] content store delete failed for %s: %s",
                    memory_id,
                    type(exc).__name__,
                )
                content_delete_failed += 1

    qdrant_deleted = 0
    for memory_id in ids:
        doc = plan["docs_by_id"].get(memory_id) or {}
        if await index_delete(str(doc.get("user_id") or ""), memory_id):
            qdrant_deleted += 1
    return {
        "deleted": deleted,
        "qdrant_deleted": qdrant_deleted,
        "content_deleted": content_deleted,
        "content_delete_failed": content_delete_failed,
    }


def confirm_apply(plan: dict[str, Any], *, assume_yes: bool = False) -> bool:
    """批量删除前的确认门：--yes 直接过；否则必须逐字输入 DELETE。"""
    total = len(plan.get("duplicates") or []) + len(plan.get("junk_ids") or [])
    if assume_yes:
        return True
    if total <= 0:
        return True
    try:
        answer = input(f"Type DELETE to permanently remove {total} memories: ")
    except EOFError:
        return False
    return answer.strip() == "DELETE"


def render_report(plan: dict[str, Any]) -> str:
    # 脱敏：只列 memory_id 与计数，不输出标题/摘要/LLM 理由等用户记忆内容
    lines = [
        f"total memories scanned: {plan['total']}",
        "",
        f"== near-duplicates to delete ({len(plan['duplicates'])}) ==",
    ]
    for item in plan["duplicates"]:
        lines.append(f"  [dup] {item['memory_id']}")
    junk = [j for j in plan["judgments"] if not j["keep"]]
    lines.append("")
    lines.append(f"== durability review: JUNK ({len(junk)}) / judged ({len(plan['judgments'])}) ==")
    for j in junk:
        lines.append(f"  [junk] {j['memory_id']}")
    lines.append("")
    lines.append("dry-run: no changes written. pass --apply to delete the entries above.")
    return "\n".join(lines)


async def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="execute deletions (default dry-run)")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the interactive DELETE confirmation for --apply",
    )
    parser.add_argument("--user", dest="user_id", default=None, help="restrict to one user_id")
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="run LLM durability review (up to 500 model calls)",
    )
    parser.add_argument(
        "--dup-threshold",
        type=float,
        default=DEFAULT_DUP_THRESHOLD,
        help="embedding cosine duplicate threshold (default 0.8)",
    )
    args = parser.parse_args(argv)

    from src.infra.storage.mongodb import get_mongo_client

    client = get_mongo_client()
    collection = client[settings.MONGODB_DB]["native_memories"]

    plan = await plan_cleanup(
        collection,
        user_id=args.user_id,
        use_llm=args.with_llm,
        dup_threshold=args.dup_threshold,
    )
    print(render_report(plan))
    if args.apply:
        if not (plan["duplicates"] or plan["junk_ids"]):
            print("\nnothing to delete.")
            return 0
        if not confirm_apply(plan, assume_yes=args.yes):
            print("\naborted: confirmation required to delete (type DELETE, or pass --yes).")
            return 1
        result = await apply_cleanup(collection, plan)
        print(f"\napplied: {json.dumps(result, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
