"""模型 max_tokens / 输入预算相关的共享常量与守卫。

背景（2026-09-21 生产事故）：deepagents SummarizationMiddleware 的输入预算
公式为 ``int(max_input_tokens * 0.95) - max_tokens``。生产 zai 系模型曾配置
max_tokens=131072，把预算挤到 58,928——低于「压缩摘要 + 保留尾部 +
system/tools」的不可再压最小值，长会话在压缩后仍超预算，终态
ContextOverflowError 卡死。本模块集中存放相关默认值与诊断告警，
供 client.py 构建模型时调用。
"""

from __future__ import annotations

from typing import Optional

from src.infra.logging import get_logger

logger = get_logger(__name__)

# Anthropic Messages API 强制要求 max_tokens 字段，无法做到「未配置就不发送」；
# langchain-anthropic 对 None 会经 set_default_max_tokens 校验器静默填
# _FALLBACK_MAX_OUTPUT_TOKENS=4096（模型不在其内置 _MODEL_PROFILES 注册表时必
# 命中），4096 会截断 agent 长输出。未配置时注入该显式默认保持行为可预期。
ANTHROPIC_DEFAULT_MAX_TOKENS = 32_768

# 输入预算低于该下限时长会话压缩后仍可能超预算（终态 ContextOverflowError），
# 构建模型时告警留下诊断线索。
INPUT_BUDGET_WARN_FLOOR = 20_000


def warn_if_input_budget_strangled(
    profile: Optional[dict],
    max_tokens: Optional[int],
    model_name: str,
) -> None:
    """按 deepagents 同款公式校验输入预算，过小时输出 WARNING。

    公式：``int(profile.max_input_tokens * 0.95) - max_tokens``；参数缺失
    （无 profile 或未配置 max_tokens）时静默跳过。
    """
    if not isinstance(profile, dict) or max_tokens is None:
        return
    limit = profile.get("max_input_tokens")
    if not isinstance(limit, int) or isinstance(limit, bool):
        return
    budget = int(limit * 0.95) - max_tokens
    if budget < INPUT_BUDGET_WARN_FLOOR:
        logger.warning(
            "[LLMClient] Tiny input budget for %s: int(%s*0.95) - %s = %s tokens; "
            "long sessions may hit terminal ContextOverflowError after compaction — "
            "raise profile.max_input_tokens or lower max_tokens",
            model_name,
            limit,
            max_tokens,
            budget,
        )
