"""usage_logs 历史费用回填。

用当前价格快照（models.dev 同步 + 模型配置覆盖）补算未计价的存量记录：
- 只处理 ``cost_available != True`` 的文档，可重复执行（幂等）
- 逐条解析价格并写入 cost_usd 快照；无法计价的按模型名汇总返回
- 注意：历史记录按「当前」价格估算，模型若曾调价会有出入
"""

from src.infra.logging import get_logger
from src.infra.pricing.calculator import compute_cost
from src.infra.pricing.locks import acquire_pricing_lock, release_pricing_lock
from src.infra.pricing.service import resolve_price
from src.infra.usage.storage import get_usage_storage

logger = get_logger(__name__)

BATCH_SIZE = 500
MAX_BATCHES = 100_000  # 安全阀：防止异常数据导致死循环
BACKFILL_LOCK_KEY = "pricing:backfill:lock"
BACKFILL_LOCK_TTL_SECONDS = 10 * 60


async def _resolve_config_id_by_value(model_value: str) -> str:
    """旧记录仅在模型配置唯一时恢复身份，不猜测同名渠道。"""
    try:
        from src.infra.agent.model_storage import get_model_storage

        docs = (
            await get_model_storage()
            ._get_collection()
            .find({"value": model_value}, {"_id": 0, "id": 1})
            .limit(2)
            .to_list(length=2)
        )
        if len(docs) != 1 or not docs[0].get("id"):
            raise ValueError("Historical model configuration is missing or ambiguous")
        return docs[0]["id"]
    except Exception as e:
        logger.debug(f"Pricing backfill: model config lookup failed for {model_value!r}: {e}")
        raise


async def backfill_usage_costs(
    *,
    dry_run: bool = False,
    batch_size: int = BATCH_SIZE,
    usage_storage=None,
) -> dict:
    """补算存量 usage_logs 的费用。

    Returns:
        {scanned, priced, still_unpriced, unpriced_models, dry_run}
    """
    usage = usage_storage or get_usage_storage()

    # 多副本互斥：其他实例正在回填时直接返回，不重复扫描；
    # Redis 故障时退化为本地执行（写入幂等）。
    lock_token = None
    lock_ok = True
    try:
        lock_token = await acquire_pricing_lock(BACKFILL_LOCK_KEY, BACKFILL_LOCK_TTL_SECONDS)
    except Exception as e:
        logger.warning(f"Pricing backfill: lock unavailable, proceeding locally: {e}")
        lock_ok = False
    if lock_ok and lock_token is None:
        logger.info("Pricing backfill: lock held by another replica, skipping")
        return _empty_summary(dry_run=dry_run, lock_contended=True)

    try:
        return await _backfill_locked(usage=usage, dry_run=dry_run, batch_size=batch_size)
    finally:
        if lock_token is not None:
            await release_pricing_lock(BACKFILL_LOCK_KEY, lock_token)


def _empty_summary(*, dry_run: bool, lock_contended: bool) -> dict:
    return {
        "scanned": 0,
        "priced": 0,
        "still_unpriced": 0,
        "unpriced_models": {},
        "dry_run": dry_run,
        "lock_contended": lock_contended,
    }


async def _backfill_locked(*, usage, dry_run: bool, batch_size: int) -> dict:
    scanned = 0
    priced = 0
    resolved_elsewhere = 0
    unpriced_models: dict[str, int] = {}
    seen: set[str] = set()

    for _ in range(MAX_BATCHES):
        docs = await usage.list_unpriced_usage_logs(limit=batch_size, exclude_trace_ids=seen)
        fresh = [doc for doc in docs if doc.get("trace_id") not in seen]
        if not fresh:
            break
        for doc in fresh:
            seen.add(doc["trace_id"])
            scanned += 1
            model_value = str(doc.get("model") or "")
            token_fields = (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_creation_tokens",
            )
            if (
                doc.get("input_includes_cache") is not True
                or doc.get("usage_incomplete") is not False
                or any(
                    not isinstance(doc.get(key), int)
                    or isinstance(doc.get(key), bool)
                    or doc[key] < 0
                    for key in token_fields
                )
            ):
                unpriced_models[model_value] = unpriced_models.get(model_value, 0) + 1
                continue
            model_config_id = doc.get("model_id") or None
            provider = None
            try:
                if not model_config_id and model_value:
                    model_config_id = await _resolve_config_id_by_value(model_value)
                if model_config_id:
                    from src.infra.agent.model_storage import get_model_storage

                    model = await get_model_storage().get(model_config_id)
                    if not model or (model_value and model_value != model.value):
                        raise ValueError("Historical model identity cannot be restored")
                    model_value = model.value
                    provider = model.provider
            except Exception as error:
                logger.debug("Pricing backfill: model identity unresolved: %s", error)
                unpriced_models[model_value] = unpriced_models.get(model_value, 0) + 1
                continue

            resolved = await resolve_price(
                value=model_value or None, model_config_id=model_config_id, provider=provider
            )
            cost = None
            if resolved is not None:
                cost = compute_cost(
                    input_tokens=int(doc.get("input_tokens") or 0),
                    output_tokens=int(doc.get("output_tokens") or 0),
                    cache_read_tokens=int(doc.get("cache_read_tokens") or 0),
                    cache_creation_tokens=int(doc.get("cache_creation_tokens") or 0),
                    rates=resolved.rates,
                )
            if cost is None:
                unpriced_models[model_value] = unpriced_models.get(model_value, 0) + 1
                continue
            if dry_run or await usage.update_usage_cost(
                doc["trace_id"],
                cost.total_usd,
                expected_usage={
                    **{key: doc[key] for key in token_fields},
                    "model": doc.get("model"),
                    "model_id": doc.get("model_id"),
                },
            ):
                priced += 1
            else:
                current = await usage.collection.find_one(
                    {"trace_id": doc["trace_id"]},
                    {"cost_available": 1, "usage_incomplete": 1, "input_includes_cache": 1},
                )
                if (
                    current
                    and current.get("cost_available") is True
                    and current.get("usage_incomplete") is False
                    and current.get("input_includes_cache") is True
                ):
                    resolved_elsewhere += 1
                else:
                    unpriced_models[model_value] = unpriced_models.get(model_value, 0) + 1

    summary = {
        "scanned": scanned,
        "priced": priced,
        "still_unpriced": scanned - priced - resolved_elsewhere,
        "unpriced_models": unpriced_models,
        "dry_run": dry_run,
        "lock_contended": False,
    }
    logger.info(f"Pricing backfill: {summary}")
    return summary
