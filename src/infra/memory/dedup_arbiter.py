"""写时语义去重的 System One 仲裁。

现行规则是 embedding 余弦单阈值 0.88（classification.SEMANTIC_DEDUP_THRESHOLD）：
改写通常 ≥0.9、相关但不同的事实通常 0.8x 以下——两端都是错判带。本模块在
灰区引入 System One「是否同一底层事实」判定（提示词与评估脚本一致，实测
152 对生产样本三余弦带干净分离 0.004/0.980）。

模式（MEMORY_DEDUP_SYSTEMONE_MODE）：
- off：行为与 find_semantic_memory_match 完全一致（默认）
- shadow：按现行 0.88 规则返回，同时记录灰区仲裁结果供观察
- arbitrate：≥gray_high 直接同条；灰区 p_same ≥ 阈值判同条、否则新建；
  <gray_low 直接新建；判定失败回退 0.88 规则（fail-open）
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.infra.decision.client import is_systemone_configured, judge_noul
from src.infra.memory.client.native.classification import SEMANTIC_DEDUP_THRESHOLD
from src.infra.memory.client.native.models import cosine_similarity
from src.kernel.config import settings

logger = logging.getLogger(__name__)

ARBITRATE_MODE_OFF = "off"
ARBITRATE_MODE_SHADOW = "shadow"
ARBITRATE_MODE_ARBITRATE = "arbitrate"

_SAME_INSTRUCTIONS = (
    "Do these two memory entries describe the same underlying fact, preference, "
    "or piece of knowledge about the user?"
)
_SAME_CRITERIA = {
    "true": (
        "Both entries capture the same core fact or requirement, even if worded "
        "differently or with different detail levels"
    ),
    "false": (
        "The entries are about different topics, different objects, or genuinely distinct facts"
    ),
}


def _settings() -> dict[str, Any]:
    return {
        "mode": str(
            getattr(settings, "MEMORY_DEDUP_SYSTEMONE_MODE", ARBITRATE_MODE_OFF)
            or ARBITRATE_MODE_OFF
        )
        .strip()
        .lower(),
        "gray_low": float(getattr(settings, "MEMORY_DEDUP_SYSTEMONE_GRAY_LOW", 0.75) or 0.75),
        "gray_high": float(getattr(settings, "MEMORY_DEDUP_SYSTEMONE_GRAY_HIGH", 0.92) or 0.92),
        "same_threshold": float(
            getattr(settings, "MEMORY_DEDUP_SYSTEMONE_SAME_THRESHOLD", 0.8) or 0.8
        ),
    }


async def resolve_semantic_match(
    fetch_candidates: Callable[[str], Awaitable[list[dict[str, Any]]]],
    user_id: str,
    query_embedding: list[float],
    query_summary: str,
    memory_type: str,
) -> dict[str, Any] | None:
    """带仲裁的写时同条匹配；off / 未配置退化为现行 0.88 单阈值规则。

    返回匹配的既有记忆文档（合并更新）或 None（新建）。
    """
    cfg = _settings()
    use_arbiter = cfg["mode"] in {ARBITRATE_MODE_SHADOW, ARBITRATE_MODE_ARBITRATE} and (
        is_systemone_configured()
    )

    best_match: dict[str, Any] | None = None
    best_score = 0.0
    if query_embedding:
        candidates = await fetch_candidates(user_id)
        for doc in candidates:
            if doc.get("memory_type") != memory_type:
                continue
            embedding = doc.get("embedding")
            if not embedding:
                continue
            score = cosine_similarity(query_embedding, embedding)
            if score >= best_score:
                best_score = score
                best_match = doc

    # off / 未配置：与 find_semantic_memory_match 完全一致
    if not use_arbiter:
        return best_match if best_score >= SEMANTIC_DEDUP_THRESHOLD else None

    # 高带：无需仲裁直接同条（现行规则下 0.88~gray_high 的段位也并入高带）
    if best_match is not None and best_score >= cfg["gray_high"]:
        return best_match

    legacy_outcome = best_match if best_score >= SEMANTIC_DEDUP_THRESHOLD else None
    if best_match is None or best_score < cfg["gray_low"]:
        return legacy_outcome

    # 灰区：System One 仲裁（state 含用户记忆内容，日志只记分数不记内容）
    state = (
        f"Memory A (new)\nSummary: {query_summary}\n\n"
        f"Memory B (existing, memory_id={best_match.get('memory_id')})\n"
        f"Summary: {best_match.get('summary') or ''}"
    )
    p_same = await judge_noul(state, _SAME_INSTRUCTIONS, criteria=_SAME_CRITERIA)

    if p_same is None:
        logger.warning(
            "[MemoryDedup] systemone arbitration unavailable, falling back to %.2f rule: memory_id=%s score=%.3f",
            SEMANTIC_DEDUP_THRESHOLD,
            best_match.get("memory_id"),
            best_score,
        )
        return legacy_outcome

    arbitrated_same = p_same >= cfg["same_threshold"]
    if cfg["mode"] == ARBITRATE_MODE_ARBITRATE:
        if arbitrated_same:
            logger.info(
                "[MemoryDedup] systemone merge: memory_id=%s score=%.3f p_same=%.3f",
                best_match.get("memory_id"),
                best_score,
                p_same,
            )
            return best_match
        logger.info(
            "[MemoryDedup] systemone keep-separate: memory_id=%s score=%.3f p_same=%.3f",
            best_match.get("memory_id"),
            best_score,
            p_same,
        )
        return None

    logger.info(
        "[MemoryDedup] systemone shadow: memory_id=%s score=%.3f p_same=%.3f arbitrated_same=%s legacy_merge=%s",
        best_match.get("memory_id"),
        best_score,
        p_same,
        arbitrated_same,
        legacy_outcome is not None,
    )
    return legacy_outcome
