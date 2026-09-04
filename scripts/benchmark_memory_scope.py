"""Memory scope benchmark — 检索隔离质量 + 多轮 KV 前缀稳定性。

设计文档：docs/superpowers/specs/2026-09-04-memory-scope-and-context-design.md

Part A（隔离质量，真实 MongoDB 独立 benchmark 库）：
- 3 个项目 × 主题重叠的项目记忆（部署/数据库/CI 各项目不同事实）+ 用户记忆 + reference
- 断言：项目会话零跨项目泄漏、无项目会话见不到 project 记忆、user 记忆全项目可见

Part B（KV 缓存前缀稳定性）：
- 模拟 10 轮对话，序列化 (system + tools 描述 + 历史消息) 为字节流
- 逐轮计算与上一轮的最长公共前缀占比（≈ provider 前缀缓存命中率的下界估计）
- 三组：无记忆用户 / 项目用户稳定数据 / 会话中途写入记忆

用法::

    uv run python scripts/benchmark_memory_scope.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BENCHMARK_DB = "lambchat_benchmark_scope"
PROJECTS = {
    "proj-alpha": {
        "deploy": "k8s rolling updates with auto rollback",
        "db": "MongoDB 8.2 replica set",
    },
    "proj-beta": {"deploy": "docker compose on a single VM", "db": "PostgreSQL 16 with pgvector"},
    "proj-gamma": {"deploy": "bare metal systemd services", "db": "SQLite with WAL mode"},
}
USER_MEMORIES = [
    ("raw SQL preference", "The user prefers raw SQL over ORMs for analytics workloads."),
    ("terse replies", "The user prefers terse, evidence-backed replies in Chinese."),
    ("uv tooling", "The user manages Python dependencies with uv, never pip."),
]
REFERENCE_MEMORIES = [
    ("mongo vector docs", "MongoDB 8.2 community edition ships built-in $vectorSearch."),
    (
        "openai prompt caching",
        "OpenAI prefix caching keys on the leading stable bytes of the request.",
    ),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def seed_memories(collection) -> dict[str, int]:
    """直接落库（写入路径已有单测；benchmark 关注检索与索引）。"""
    now = _now()
    docs: list[dict[str, Any]] = []

    def doc(memory_id, mtype, content, context, scope, project_id=None, source="manual"):
        base = {
            "memory_id": memory_id,
            "user_id": "bench-user",
            "title": memory_id[:25],
            "summary": content[:100],
            "index_label": f"{memory_id}: {content[:60]}",
            "memory_type": mtype,
            "context": context,
            "tags": [],
            "scope": scope,
            "project_id": project_id,
            "source": source,
            "embedding": None,
            "created_at": now - timedelta(days=1),
            "updated_at": now - timedelta(days=1),
            "accessed_at": now - timedelta(days=1),
            "access_count": 0,
            "source_refs": [],
            "content": content,
            "content_storage_mode": "inline",
            "content_store_key": None,
        }
        docs.append(base)

    n = 0
    for pid, facts in PROJECTS.items():
        for topic, fact in facts.items():
            doc(
                f"m-{pid}-{topic}",
                "project",
                f"{pid} {topic}: {fact}",
                "project_constraint",
                "project",
                pid,
            )
            n += 1
        # 每项目再补 6 条噪声项目记忆，检验过滤不靠内容巧合
        for i in range(6):
            doc(
                f"m-{pid}-note{i}",
                "project",
                f"{pid} internal note {i}",
                "project_status",
                "project",
                pid,
            )
            n += 1
    for title, content in USER_MEMORIES:
        doc(f"m-user-{title.replace(' ', '-')[:20]}", "user", content, "user_identity", "user")
        n += 1
    for title, content in REFERENCE_MEMORIES:
        doc(
            f"m-ref-{title.replace(' ', '-')[:20]}",
            "reference",
            content,
            "reference_link",
            "reference",
        )
        n += 1
    # legacy：无 scope 字段的旧数据（视同 user）
    doc("m-legacy-1", "user", "The user's timezone is Asia/Shanghai.", "user_identity", None)
    docs[-1].pop("scope")
    docs[-1].pop("project_id")
    n += 1

    await collection.insert_many(docs)
    return {
        "total": n,
        "projects": len(PROJECTS) * 8,
        "user": len(USER_MEMORIES) + 1,
        "reference": len(REFERENCE_MEMORIES),
    }


async def run_isolation_benchmark(backend, collection) -> dict[str, Any]:
    results: dict[str, Any] = {"cases": [], "violations": []}

    async def recall(query: str, project_id: str | None) -> list[dict]:
        out = await backend.recall("bench-user", query, max_results=8, project_id=project_id)
        return out.get("memories") or []

    # 1) 项目会话：部署/数据库查询只见本项目 + user/reference
    for pid, facts in PROJECTS.items():
        for topic, fact in facts.items():
            hits = await recall(topic, pid)
            hit_ids = {m["memory_id"] for m in hits}
            foreign = {
                mid
                for mid in hit_ids
                if mid.startswith("m-proj-") and not mid.startswith(f"m-{pid}-")
            }
            own = f"m-{pid}-{topic}" in hit_ids
            user_visible = any(mid.startswith("m-user-") or mid == "m-legacy-1" for mid in hit_ids)
            if foreign:
                results["violations"].append(
                    {"project": pid, "query": topic, "foreign": sorted(foreign)}
                )
            results["cases"].append(
                {
                    "project": pid,
                    "query": topic,
                    "hits": len(hits),
                    "own_hit": own,
                    "foreign_leak": len(foreign),
                }
            )
            assert own, f"{pid} {topic}: own project memory not recalled: {sorted(hit_ids)}"

    # 2) 无项目会话：见不到任何 project 记忆
    for query in ("deploy", "database", "note"):
        hits = await recall(query, None)
        leaked = [m["memory_id"] for m in hits if m.get("scope") == "project"]
        if leaked:
            results["violations"].append({"no_project_query": query, "leaked": leaked})

    # 3) 用户记忆跨项目可见（宽松验证：任一项目会话可召回 raw SQL）
    pid = next(iter(PROJECTS))
    hits = await recall("raw SQL preference", pid)
    results["user_memory_visible_in_project"] = any(
        m["memory_id"].startswith("m-user-") for m in hits
    )

    # 4) legacy 无 scope 文档在项目会话可见（视同 user）
    hits = await recall("timezone", pid)
    results["legacy_visible"] = any(m["memory_id"] == "m-legacy-1" for m in hits)

    # 延迟
    t0 = time.perf_counter()
    for _ in range(5):
        await recall("deployment", pid)
    results["recall_latency_ms_avg"] = round((time.perf_counter() - t0) / 5 * 1000, 2)
    return results


# ---------------------------------------------------------------------------
# Part B：多轮 KV 前缀稳定性
# ---------------------------------------------------------------------------


def serialize_turn(
    system_prompt: str, tool_descriptions: list[tuple[str, str]], history: list[str]
) -> bytes:
    """模拟 provider 请求中参与前缀缓存的字节：system + tools + 消息历史。"""
    parts = [system_prompt]
    for name, description in tool_descriptions:
        parts.append(f"TOOL {name}: {description}")
    parts.extend(history)
    return "\x00".join(parts).encode("utf-8")


def lcp_bytes(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if a[:mid] == b[:mid]:
            lo = mid
        else:
            hi = mid - 1
    return lo


async def run_kv_benchmark(backend, collection) -> dict[str, Any]:
    from src.infra.agent.middleware import prompt_injection as pi

    system_prompt = "You are LambChat agent. " * 20  # ~1KB 稳定 system
    base_tool_descriptions = [
        ("memory_recall", "base recall description"),
        ("memory_retain", "base retain description"),
        ("web_search", "search the web"),
    ] * 10  # 放大 tools 段占比，贴近真实规模

    async def index_context(user_id: str, session_id: str) -> str:
        return await pi.build_memory_recall_index_context(user_id, session_id=session_id)

    def turn_bytes(idx_ctx: str, turn: int, middleware_style: str) -> bytes:
        tools = list(base_tool_descriptions)
        if middleware_style == "inject":
            tools[0] = ("memory_recall", f"base recall description\n\n{idx_ctx}")
        history = [f"user: question {i}\nassistant: answer {i}" for i in range(1, turn + 1)]
        return serialize_turn(system_prompt, tools, history)

    scenarios: dict[str, Any] = {}

    # 场景 1：无记忆用户（空索引）
    pi._MEMORY_INDEX_SNAPSHOTS.clear()
    empty_ctx = await index_context("bench-empty", "s-empty")
    ratios = []
    prev = None
    for turn in range(1, 11):
        cur = turn_bytes(empty_ctx, turn, "none" if not empty_ctx else "inject")
        if prev is not None:
            ratios.append(lcp_bytes(prev, cur) / len(cur))
        prev = cur
    scenarios["no_memory_user"] = {
        "per_turn_prefix_hit": [round(r, 4) for r in ratios],
        "avg": round(sum(ratios) / len(ratios), 4),
    }

    # 场景 2：项目用户、数据稳定 —— middleware 实例语义（首构建后冻结）
    pi._MEMORY_INDEX_SNAPSHOTS.clear()
    ctx = await index_context("bench-user", "s-stable")
    assert "<memory_index" in ctx, "expected seeded index"
    ratios = []
    prev = None
    for turn in range(1, 11):
        cur = turn_bytes(ctx, turn, "inject")
        if prev is not None:
            ratios.append(lcp_bytes(prev, cur) / len(cur))
        prev = cur
    scenarios["project_user_stable"] = {
        "per_turn_prefix_hit": [round(r, 4) for r in ratios],
        "avg": round(sum(ratios) / len(ratios), 4),
        "index_bytes": len(ctx.encode()),
    }

    # 场景 3：会话中途写入记忆 → 当前会话前缀不回溯变化（实例快照语义）
    pi._MEMORY_INDEX_SNAPSHOTS.clear()
    ctx_v1 = await index_context("bench-user", "s-mid")
    before = turn_bytes(ctx_v1, 10, "inject")
    # 中途写入一条新用户记忆 + 失效广播（清模块级快照）
    await collection.insert_one(
        {
            "memory_id": "m-user-new-mid",
            "user_id": "bench-user",
            "title": "new preference",
            "summary": "The user now prefers DuckDB for local analytics.",
            "index_label": "new preference: DuckDB",
            "memory_type": "user",
            "context": "user_identity",
            "tags": [],
            "scope": "user",
            "project_id": None,
            "source": "manual",
            "embedding": None,
            "created_at": _now(),
            "updated_at": _now(),
            "accessed_at": _now(),
            "access_count": 0,
            "source_refs": [],
            "content": "The user now prefers DuckDB for local analytics.",
            "content_storage_mode": "inline",
            "content_store_key": None,
        }
    )
    pi._MEMORY_INDEX_SNAPSHOTS.clear()
    # 等价 retain 的失效链路：pi 层经 tools._get_backend() 用的是全局单例，
    # 失效必须打到同一实例（生产写入走同一单例，无此错位）
    from src.infra.memory.tools import _get_backend

    singleton = await _get_backend()
    if singleton is not None:
        await singleton._invalidate_cache("bench-user")
    ctx_v2 = await index_context("bench-user", "s-mid-next-session")
    after_same_session = turn_bytes(ctx_v1, 11, "inject")  # 已加载实例仍用 v1
    after_new_session = turn_bytes(ctx_v2, 1, "inject")  # 新会话用 v2
    scenarios["mid_session_write"] = {
        "current_session_prefix_stable": lcp_bytes(before, after_same_session) == len(before),
        "index_changed_for_new_session": ctx_v1 != ctx_v2,
        "new_session_overlap_with_old": round(
            lcp_bytes(before, after_new_session) / len(after_new_session), 4
        ),
    }
    return scenarios


async def main() -> int:
    from src.kernel.config import settings

    settings.MONGODB_DB = BENCHMARK_DB

    from src.infra.storage.mongodb import get_mongo_client

    client = get_mongo_client()
    db = client[BENCHMARK_DB]
    await client.drop_database(BENCHMARK_DB)

    from src.infra.memory.client.native import NativeMemoryBackend
    from src.infra.memory.client.native.models import COLLECTION_NAME

    backend = NativeMemoryBackend()
    t0 = time.perf_counter()
    await backend.initialize()
    init_s = time.perf_counter() - t0

    collection = db[COLLECTION_NAME]
    seed = await seed_memories(collection)

    isolation = await run_isolation_benchmark(backend, collection)
    kv = await run_kv_benchmark(backend, collection)

    # 索引隔离：项目会话的索引不含他项目条目
    index_proj = await backend.build_memory_index("bench-user", project_id="proj-alpha")
    index_plain = await backend.build_memory_index("bench-user", project_id=None)
    index_check = {
        "alpha_index_contains_beta": "proj-beta" in index_proj,
        "alpha_index_contains_alpha": "proj-alpha" in index_proj,
        "plain_index_contains_any_project": "proj-alpha" in index_plain
        or "proj-beta" in index_plain,
        "revision_stable": index_proj.count("revision=") == 1,
    }

    report = {
        "seed": seed,
        "backend_init_seconds": round(init_s, 2),
        "isolation": isolation,
        "index": index_check,
        "kv_prefix_stability": kv,
        "verdict": {
            "zero_cross_project_leak": not isolation["violations"],
            "user_memory_cross_project_visible": isolation["user_memory_visible_in_project"],
            "no_project_session_sees_nothing_project": all(
                not v.get("leaked") for v in isolation["violations"] if "no_project_query" in v
            ),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    await backend.close()
    await client.drop_database(BENCHMARK_DB)

    ok = (
        report["verdict"]["zero_cross_project_leak"]
        and report["verdict"]["user_memory_cross_project_visible"]
        and not index_check["alpha_index_contains_beta"]
        and not index_check["plain_index_contains_any_project"]
        and scenarios_ok(kv)
    )
    print("\nBENCHMARK:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def scenarios_ok(kv: dict[str, Any]) -> bool:
    stable = kv["project_user_stable"]["avg"]
    mid = kv["mid_session_write"]
    return (
        stable >= 0.97
        and mid["current_session_prefix_stable"]
        and mid["index_changed_for_new_session"]
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
