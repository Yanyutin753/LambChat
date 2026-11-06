"""Tariffs for the exact auxiliary endpoints used by LambChat, in CNY / million inputs."""

import math

from src.infra.pricing.service import get_fx_rates

# SiliconFlow CN published tariffs, and the operator's matching self-hosted decision rate.
# https://siliconflow.cn/pricing
_INPUT_CNY = {
    ("embedding", "https://api.siliconflow.cn", "Qwen/Qwen3-Embedding-0.6B"): 0.07,
    ("rerank", "https://api.siliconflow.cn", "BAAI/bge-reranker-v2-m3"): 0.0,
    ("decision", "http://127.0.0.1:18001", "apus-openjev-4b-5949"): 0.07,
}


def model_counts(operation, payload):
    payload = payload if isinstance(payload, dict) else {}
    usage = payload.get("usage")
    if operation == "rerank":
        meta = payload.get("meta")
        usage = meta.get("billed_units") if isinstance(meta, dict) else None
    usage = usage if isinstance(usage, dict) else {}

    def counter(key, default=None):
        value = usage.get(key, default)
        return value if type(value) is int and 0 <= value < 2**63 else None

    if operation == "embedding":
        inputs, outputs = counter("prompt_tokens"), counter("completion_tokens", 0)
    else:
        inputs, outputs = counter("input_tokens"), counter("output_tokens")
    # The legacy OpenJet adapter returned zero for every processed prompt.
    if operation == "decision" and inputs == 0:
        inputs = None
    total = inputs + outputs if inputs is not None and outputs is not None else None
    if "total_tokens" in usage and counter("total_tokens") != total:
        inputs = outputs = total = None
    return dict(
        input_tokens=inputs,
        output_tokens=outputs,
        total_tokens=total,
        cache_read_tokens=0,
        cache_creation_tokens=0,
    )


async def input_cost_usd(operation, base, model, counts):
    rate = _INPUT_CNY.get((operation, base.rstrip("/"), model))
    if rate is None or counts["input_tokens"] is None:
        return None
    if rate == 0:
        return 0.0
    fx = await get_fx_rates() or {}
    rates = fx.get("rates")
    cny = rates.get("CNY") if isinstance(rates, dict) else None
    if (
        fx.get("base") != "USD"
        or isinstance(cny, bool)
        or not isinstance(cny, (int, float))
        or not math.isfinite(cny)
        or cny <= 0
    ):
        return None
    return round(counts["input_tokens"] * rate / 1_000_000 / cny, 12)
