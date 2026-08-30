"""trace 完成后的 usage_logs 落库与前端 WS 刷新通知。"""

from src.infra.logging import get_logger
from src.infra.session.trace_storage import get_trace_storage
from src.infra.websocket import get_connection_manager
from src.kernel.config import settings

logger = get_logger(__name__)


async def _write_usage_log(trace_id: str) -> None:
    """在 trace 完成后，异步将 token 用量写入独立的 usage_logs 集合。"""
    try:
        from src.infra.usage.storage import get_usage_storage

        storage = get_usage_storage()
        collection = storage.collection

        # 只读取 trace 元数据；usage 事件通过兼容读路径从 chunk/legacy 中查询。
        trace_doc = await collection.database[settings.MONGODB_TRACES_COLLECTION].find_one(
            {"trace_id": trace_id},
            {"_id": 0, "events": 0},
        )
        if trace_doc:
            trace_storage = get_trace_storage()
            usage_event = await trace_storage.get_last_trace_event(
                trace_id,
                ["token:usage"],
            )
            # 失败的任务也要记录原因（最后一个 error 事件），供用量面板展示
            error_event = await trace_storage.get_last_trace_event(
                trace_id,
                ["error"],
            )
            await storage.upsert_usage_log_from_trace_metadata(
                trace_doc,
                (usage_event or {}).get("data", {}),
                error_data=(error_event or {}).get("data", {}),
            )
            # 落库完成后通过 WS 通知前端刷新当日用量；消息到达时数据已可查
            user_id = trace_doc.get("user_id")
            if user_id:
                await get_connection_manager().send_to_user_with_broadcast(
                    str(user_id),
                    {"type": "usage:updated", "data": {"trace_id": trace_id}},
                )
    except Exception as e:
        # 写入 usage_logs 失败不应影响主流程
        logger.warning(f"Failed to write usage log for trace {trace_id}: {e}")
