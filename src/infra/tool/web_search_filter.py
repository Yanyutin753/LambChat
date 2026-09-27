"""web_search 结果的 System One 相关性预筛。

search agent 是流量主体，而搜索结果里混着大量无关 snippet（实测 150 次生产
调用 / 567 条 snippet：44.1% 判为垃圾、20% 调用整卡可丢，低分样本人工核验
非误杀）。预筛在结果进模型上下文前把垃圾丢掉，直接省 token 提质量。

模式（WEB_SEARCH_SYSTEMONE_MODE）：
- off：不过滤（默认）
- shadow：只记录判定分布不生效，供观察
- filter：相关性 < 阈值的结果丢弃，但每次调用至少保留得分最高的一条
  （实测 0.05 以下为纯垃圾带；判定失败 fail-open 保留该条结果）
"""

from __future__ import annotations

import logging
from typing import Any

from src.infra.decision.client import is_systemone_configured, judge_noul
from src.kernel.config import settings

logger = logging.getLogger(__name__)

FILTER_MODE_OFF = "off"
FILTER_MODE_SHADOW = "shadow"
FILTER_MODE_FILTER = "filter"

_RELEVANCE_INSTRUCTIONS = (
    "Is this search result relevant and useful for answering the search query?"
)


def _settings() -> dict[str, Any]:
    return {
        "mode": str(
            getattr(settings, "WEB_SEARCH_SYSTEMONE_MODE", FILTER_MODE_OFF) or FILTER_MODE_OFF
        )
        .strip()
        .lower(),
        "threshold": float(
            getattr(settings, "WEB_SEARCH_SYSTEMONE_RELEVANCE_THRESHOLD", 0.05) or 0.05
        ),
    }


def _result_state(query: str, result: dict[str, Any]) -> str:
    title = str(result.get("title") or "")[:120]
    snippet = str(result.get("snippet") or "")[:300]
    return f"Search query: {query}\n\nSearch result:\n{title}\n{snippet}"


async def filter_web_search_results(
    query: str, results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """按相关性预筛搜索结果；off / 未配置 / 全部判定失败时原样返回。"""
    cfg = _settings()
    if cfg["mode"] == FILTER_MODE_OFF or not results:
        return results
    if not is_systemone_configured():
        return results

    scored: list[tuple[float | None, dict[str, Any]]] = []
    for result in results:
        p = await judge_noul(_result_state(query, result), _RELEVANCE_INSTRUCTIONS)
        scored.append((p, result))

    if all(p is None for p, _ in scored):
        logger.warning("[WebSearch] systemone filter unavailable, keeping all results")
        return results

    threshold = cfg["threshold"]
    keep = [r for p, r in scored if p is None or p >= threshold]
    dropped = sum(1 for p, _ in scored if p is not None and p < threshold)

    if cfg["mode"] == FILTER_MODE_SHADOW:
        values = [p for p, _ in scored if p is not None]
        logger.info(
            "[WebSearch] systemone shadow: query=%s n=%d would_drop=%d max_p=%.3f min_p=%.3f",
            query[:60],
            len(scored),
            dropped,
            max(values) if values else -1,
            min(values) if values else -1,
        )
        return results

    # filter 模式：至少保留得分最高的一条，防止整卡误杀
    if not keep and scored:
        best = max(
            scored,
            key=lambda pair: pair[0] if pair[0] is not None else -1,
        )
        keep = [best[1]]
        dropped -= 1
    if dropped:
        logger.info(
            "[WebSearch] systemone filter: query=%s kept=%d dropped=%d threshold=%.2f",
            query[:60],
            len(keep),
            dropped,
            threshold,
        )
    return keep
