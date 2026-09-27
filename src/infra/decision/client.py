"""System One 决策模型客户端：/v1/systemone 协议（TypeSafe Jev / 自托管 von）。

面向高频小判定（分类 / 是非 / 评分）的独立裸 httpx 客户端，与 embedding /
rerank 客户端同款契约：不经 LLMClient、无重试、失败返回 None 由调用方走
原路径兜底。自托管 von（Apache 2.0 开源 System One 模型）协议完全兼容，
base 指向 von serve 即可，无鉴权时 key 可留空。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.kernel.config import settings

logger = logging.getLogger(__name__)


def systemone_settings() -> dict[str, Any]:
    """集中读取 System One 配置（便于测试覆写，同 extraction_settings 思路）。"""
    return {
        "base": str(getattr(settings, "SYSTEMONE_API_BASE", "") or "").strip(),
        "key": str(getattr(settings, "SYSTEMONE_API_KEY", "") or "").strip(),
        "model": str(getattr(settings, "SYSTEMONE_MODEL", "") or "jev-latest").strip(),
        "timeout": float(getattr(settings, "SYSTEMONE_TIMEOUT_SECONDS", 5.0) or 5.0),
    }


def is_systemone_configured() -> bool:
    return bool(systemone_settings()["base"])


async def system_one(
    state: Any,
    questions: dict[str, dict[str, Any]],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, dict[str, Any]] | None:
    """执行一次 System One 求值，返回 answers 映射；未配置或任何失败返回 None。

    state 含用户会话内容，日志只记异常类型，不得记录请求内容。
    """
    cfg = systemone_settings()
    if not cfg["base"]:
        return None

    headers = {"Content-Type": "application/json"}
    if cfg["key"]:
        headers["Authorization"] = f"Bearer {cfg['key']}"

    try:
        async with httpx.AsyncClient(
            base_url=cfg["base"].rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(cfg["timeout"]),
            transport=transport,
        ) as client:
            response = await client.post(
                "/v1/systemone",
                json={"state": state, "model": cfg["model"], "questions": questions},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("[SystemOne] request failed: %s", type(exc).__name__)
        return None

    answers = payload.get("answers") if isinstance(payload, dict) else None
    if not isinstance(answers, dict):
        logger.warning("[SystemOne] malformed response: answers missing")
        return None
    return answers


async def judge_noul(
    state: Any,
    instructions: str,
    *,
    criteria: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> float | None:
    """单条是非判定：返回 P(yes)∈[0,1]；未配置或失败返回 None。"""
    question: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if criteria:
        question["criteria"] = criteria
    answers = await system_one(state, {"q": question}, transport=transport)
    if answers is None:
        return None
    answer = answers.get("q")
    value = answer.get("noul") if isinstance(answer, dict) else None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        logger.warning("[SystemOne] malformed noul answer")
        return None
    return max(0.0, min(1.0, float(value)))
