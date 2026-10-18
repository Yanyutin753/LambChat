"""
Usage storage layer.

独立的 usage_logs 集合，逐次调用更新累计 token 消耗，trace 完成时更新终态。
查询时直接从该集合读取，避免对 traces 集合做复杂聚合。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

from src.infra.logging import get_logger
from src.infra.storage.mongodb import get_mongo_client
from src.infra.usage.cost_certainty import (
    COMPLETE_USAGE_CONDITION,
    _boolean_condition,
    _cost_certainty_aggregates,
    _usage_cost_fields,
    _usage_snapshot_query,
    _valid_cost,
)
from src.infra.usage.cost_certainty import (
    PRICED_USAGE_CONDITION as PRICED_USAGE_CONDITION,
)
from src.infra.usage.counter_availability import _counter_availability_aggregates, _token_sum
from src.infra.usage.formatting import (
    _aggregate_cache_unknown_requests,
    _as_float,
    _as_int,
    _empty_dashboard,
    _empty_stats,
    _format_cost_certainty,
    _format_counter_availability,
    _format_dashboard,
)
from src.infra.usage.formatting import (
    _cache_read_share as _cache_read_share,
)
from src.infra.usage.formatting import (
    _format_ranking_item as _format_ranking_item,
)
from src.infra.utils.datetime import parse_iso
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode

logger = get_logger(__name__)

USAGE_LOG_LIMIT_MAX = 200
USAGE_RANKING_LIMIT = 8


CACHE_METRICS_CONDITION = _boolean_condition("cache_metrics_available", True)
CERTIFIED_CACHE_METRICS_CONDITION = {
    "$and": [CACHE_METRICS_CONDITION, _boolean_condition("input_includes_cache", True)]
}
SCHEDULED_USAGE_CONDITION = {
    "$or": [
        {"$eq": ["$source", "scheduled_task"]},
        {
            "$and": [
                {"$ne": ["$scheduled_task_id", None]},
                {"$ne": ["$scheduled_task_id", ""]},
            ]
        },
    ]
}


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return parse_iso(value)
        except ValueError:
            return None
    return None


def _parse_date_filter(value: str) -> datetime:
    """查询入口的显式日期过滤：非法值统一 400，而不是 500 或静默吞错。"""
    try:
        return parse_iso(value)
    except (ValueError, TypeError):
        raise AppError(ErrorCode.INVALID_DATE_FORMAT, args={"value": value}) from None


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _merge_metadata_value(
    metadata: Dict[str, Any], session_metadata: Dict[str, Any], key: str
) -> str:
    return _as_str(metadata.get(key)) or _as_str(session_metadata.get(key))


class UsageStorage:
    """使用日志存储 — 独立的 usage_logs 集合"""

    def __init__(self):
        self._collection = None

    @property
    def collection(self):
        """延迟加载 usage_logs 集合"""
        if self._collection is None:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[settings.MONGODB_USAGE_LOGS_COLLECTION]
        return self._collection

    async def ensure_indexes(self) -> None:
        """创建索引"""
        try:
            await self.collection.create_index(
                "trace_id",
                unique=True,
                name="trace_id_unique_idx",
            )
            await self.collection.create_index([("user_id", 1), ("started_at", -1)])
            await self.collection.create_index([("started_at", -1)])
            await self.collection.create_index([("model", 1), ("started_at", -1)])
            await self.collection.create_index([("team_id", 1), ("started_at", -1)])
            await self.collection.create_index([("persona_preset_id", 1), ("started_at", -1)])
            await self.collection.create_index([("source", 1), ("started_at", -1)])
            logger.info("Usage logs indexes ensured")
        except Exception as e:
            logger.error(f"Failed to create usage logs indexes: {e}")

    async def _get_session_metadata(self, session_id: str) -> Dict[str, Any]:
        if not session_id:
            return {}
        try:
            from src.infra.session.storage import SessionStorage

            doc = await SessionStorage().collection.find_one(
                {"session_id": session_id},
                {"_id": 0, "metadata": 1},
            )
            metadata = (doc or {}).get("metadata") or {}
            return metadata if isinstance(metadata, dict) else {}
        except Exception as e:
            logger.debug("Failed to load session metadata for usage log %s: %s", session_id, e)
            return {}

    async def _resolve_team_name(self, team_id: str) -> str:
        if not team_id:
            return ""
        try:
            from bson import ObjectId

            from src.infra.team.storage import TeamStorage

            query_id: ObjectId | str
            try:
                query_id = ObjectId(team_id)
            except Exception:
                query_id = team_id
            doc = await TeamStorage().collection.find_one({"_id": query_id}, {"_id": 0, "name": 1})
            return _as_str((doc or {}).get("name"))
        except Exception as e:
            logger.debug("Failed to resolve team name for usage log %s: %s", team_id, e)
            return ""

    async def upsert_usage_log(self, trace_doc: Dict[str, Any]) -> bool:
        """
        从 trace 文档提取 token:usage 数据，写入 usage_logs 集合。

        在 trace 完成时调用，将扁平化的使用记录存入独立集合。

        Args:
            trace_doc: trace 完整文档（包含 events 数组和 metadata）

        Returns:
            是否写入成功
        """
        trace_id = trace_doc.get("trace_id")
        if not trace_id:
            return False

        # 从 events 中找到最后一个 token:usage 事件
        usage_event = None
        error_event = None
        for event in reversed(trace_doc.get("events", [])):
            if usage_event is not None and error_event is not None:
                break
            if event.get("event_type") == "token:usage" and usage_event is None:
                usage_event = event.get("data", {})
            elif event.get("event_type") == "error" and error_event is None:
                error_event = event.get("data", {})

        return await self.upsert_usage_log_from_trace_metadata(
            trace_doc, usage_event, error_data=error_event
        )

    async def upsert_usage_log_from_trace_metadata(
        self,
        trace_doc: Dict[str, Any],
        usage_data: Optional[Dict[str, Any]],
        error_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        使用 trace 元数据和已解析的 token:usage 数据写入 usage_logs。

        Args:
            trace_doc: trace 元数据（不需要包含完整 events）
            usage_data: 最后一条 token:usage；缺失计数只保留占位下界，不证明零费用
            error_data: 最后一条 error 事件的 data；失败任务记录原因

        Returns:
            是否写入成功
        """
        trace_id = trace_doc.get("trace_id")
        if not trace_id:
            return False

        metadata = trace_doc.get("metadata", {}) or {}
        session_metadata = await self._get_session_metadata(str(trace_doc.get("session_id") or ""))
        usage_data = usage_data or {}
        input_tokens = _as_int(usage_data.get("input_tokens", 0))
        output_tokens = _as_int(usage_data.get("output_tokens", 0))
        total_tokens = _as_int(usage_data.get("total_tokens", 0))
        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens

        team_id = _merge_metadata_value(metadata, session_metadata, "team_id")
        team_name = _merge_metadata_value(
            metadata, session_metadata, "team_name"
        ) or await self._resolve_team_name(team_id)

        error_data = error_data or {}
        error_message = _as_str(error_data.get("error"))[:300]
        error_type = _as_str(error_data.get("type"))
        status = trace_doc.get("status", "unknown")
        token_fields = (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_creation_tokens",
        )
        fields = {*token_fields, "total_tokens"}
        supplied_unknown = usage_data.get("unknown_usage_fields")
        if isinstance(supplied_unknown, list) and all(
            isinstance(key, str) and key in fields for key in supplied_unknown
        ):
            unknown_fields = set(supplied_unknown)
        elif usage_data.get("usage_incomplete") is False:
            unknown_fields = set()
        else:
            unknown_fields = set(fields)
        for key in token_fields:
            if (
                not isinstance(usage_data.get(key), int)
                or isinstance(usage_data.get(key), bool)
                or usage_data[key] < 0
            ):
                unknown_fields.add(key)
        if usage_data.get("usage_incomplete") is True and not unknown_fields:
            unknown_fields.update(fields)
        usage_incomplete = bool(unknown_fields)
        reported_rates = usage_data.get("cost_rates")
        pricing_incomplete = isinstance(reported_rates, dict) and (
            _as_int(usage_data.get("cache_read_tokens")) > 0
            and reported_rates.get("cache_read") is None
            or _as_int(usage_data.get("cache_creation_tokens")) > 0
            and reported_rates.get("cache_write") is None
            and reported_rates.get("cache_write_included") is not True
        )
        if status == "cancelled" and not error_message:
            # 取消路径竞态：API 副本先终结 trace、worker 的 error 事件后落库时
            # 没有 error 事件可读——从 trace 元数据兜底，面板才不会显示空原因
            cancel_reason = _as_str(metadata.get("cancel_reason"))
            error_message = (cancel_reason or "Task cancelled")[:300]
            error_type = error_type or "cancelled"

        doc = {
            "trace_id": trace_id,
            "trace_event_revision": _as_int(trace_doc.get("event_revision", 0)),
            "session_id": trace_doc.get("session_id", ""),
            "run_id": trace_doc.get("run_id", ""),
            "user_id": trace_doc.get("user_id", ""),
            "username": metadata.get("username", ""),
            "agent_id": trace_doc.get("agent_id", ""),
            "agent_name": metadata.get("agent_name", ""),
            "team_id": team_id,
            "team_name": team_name,
            "persona_preset_id": _merge_metadata_value(
                metadata, session_metadata, "persona_preset_id"
            ),
            "persona_preset_name": _merge_metadata_value(
                metadata, session_metadata, "persona_preset_name"
            ),
            "source": _merge_metadata_value(metadata, session_metadata, "source") or "chat",
            "scheduled_task_id": _merge_metadata_value(
                metadata, session_metadata, "scheduled_task_id"
            ),
            "scheduled_task_run_id": _merge_metadata_value(
                metadata, session_metadata, "scheduled_task_run_id"
            ),
            "scheduled_task_trigger_type": _merge_metadata_value(
                metadata, session_metadata, "scheduled_task_trigger_type"
            )
            or _merge_metadata_value(metadata, session_metadata, "trigger_type"),
            "model": usage_data.get("model") or metadata.get("model") or "",
            "model_id": usage_data.get("model_id") or metadata.get("model_id") or "",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cache_creation_tokens": _as_int(usage_data.get("cache_creation_tokens", 0)),
            "cache_read_tokens": _as_int(usage_data.get("cache_read_tokens", 0)),
            "cost_usd": _as_float(usage_data.get("cost_usd", 0.0)),
            "cost_complete": usage_data.get("cost_complete") is True
            and _valid_cost(usage_data.get("cost_usd")),
            "cost_rates": {
                key: reported_rates.get(key)
                for key in ("input", "output", "cache_read", "cache_write", "cache_write_included")
            }
            if isinstance(reported_rates, dict)
            else None,
            "usage_incomplete": usage_incomplete,
            "unknown_usage_fields": sorted(unknown_fields),
            "input_includes_cache": usage_data.get("input_includes_cache") is True,
            "cache_metrics_available": not {
                "input_tokens",
                "cache_read_tokens",
            }.intersection(unknown_fields)
            and (
                input_tokens > 0
                and usage_data.get("cache_read_tokens") == 0
                or usage_data.get("input_includes_cache") is True
                and 0 <= _as_int(usage_data.get("cache_read_tokens")) <= input_tokens
            ),
            "cost_available": (
                "cost_usd" in usage_data
                and usage_data["cost_usd"] is not None
                and _valid_cost(usage_data["cost_usd"])
                and (not usage_incomplete or usage_data.get("cost_complete") is True)
                and not pricing_incomplete
                and usage_data.get("input_includes_cache") is True
            ),
            "duration": _as_float(usage_data.get("duration", 0.0)),
            "started_at": _as_datetime(trace_doc.get("started_at")),
            "completed_at": _as_datetime(trace_doc.get("completed_at")),
            "status": status,
            "error_message": error_message,
            "error_type": error_type,
            "step_count": _as_int(metadata.get("step_count", 0)),
            "tool_calls": _as_int(metadata.get("tool_calls", 0)),
        }
        partial_cost = usage_data.get("partial_cost_usd")
        doc["partial_cost_usd"] = (
            float(partial_cost)
            if usage_data.get("input_includes_cache") is True and _valid_cost(partial_cost)
            else None
        )
        if usage_data.get("cost_source") == "provider_settlement":
            doc.update(
                cost_source="provider_settlement",
                cost_units=usage_data.get("cost_units"),
                actual_models=usage_data.get("actual_models", []),
                model=usage_data.get("model") or "",
                model_id=usage_data.get("model_id") or "",
                cost_rates=None,
            )
        classified = _usage_cost_fields(doc)
        doc["cost_complete"] = classified["cost_complete"]
        doc["cost_available"] = classified["cost_available"]
        doc["partial_cost_usd"] = classified["partial_cost_usd"]

        try:
            auxiliary_fence: dict[str, Any] = {}
            if doc["source"] == "auxiliary":
                auxiliary_fence["cost_complete"] = {"$ne": True}
                if not doc["cost_complete"]:
                    auxiliary_fence["cost_units"] = {"$not": {"$gt": doc.get("cost_units", 0)}}
            await self.collection.update_one(
                {
                    "trace_id": trace_id,
                    **auxiliary_fence,
                    "$or": [
                        {"trace_event_revision": {"$exists": False}},
                        {"trace_event_revision": {"$lte": doc["trace_event_revision"]}},
                    ],
                },
                {"$set": doc},
                upsert=True,
            )
            return True
        except DuplicateKeyError:
            # A newer terminal snapshot won the unique trace_id upsert race.
            return False
        except Exception as e:
            logger.error(f"Failed to upsert usage log for trace {trace_id}: {e}")
            return False

    async def list_usage_logs(
        self,
        *,
        user_id: Optional[str] = None,
        model: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[List[Dict[str, Any]], int, Dict[str, Any]]:
        """
        查询使用日志列表。

        Args:
            user_id: 按用户过滤
            model: 按模型过滤
            start_date: 开始日期 (ISO string)
            end_date: 结束日期 (ISO string)
            search: 搜索用户名
            skip: 跳过数量
            limit: 返回数量

        Returns:
            (items, total, stats_dict)
        """
        limit = max(1, min(limit, USAGE_LOG_LIMIT_MAX))
        skip = max(0, skip)

        query = self._build_query(
            user_id=user_id,
            model=model,
            start_date=start_date,
            end_date=end_date,
            search=search,
        )

        try:
            # 并行执行 count + stats + items
            import asyncio

            async with asyncio.TaskGroup() as tasks:
                count_task = tasks.create_task(self._count_and_stats(query))
                items_task = tasks.create_task(self._fetch_items(query, skip, limit))
            total, stats = count_task.result()
            items = items_task.result()

            return items, total, stats
        except AppError:
            # 入参校验错误（如非法日期格式）必须冒泡为 400，不能吞成空统计
            raise
        except Exception as e:
            logger.error(f"Failed to list usage logs: {e}")
            raise

    async def get_usage_stats_only(
        self,
        *,
        user_id: Optional[str] = None,
        start_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stats-only 查询路径：跳过 items 分页 find，只做计数 + 聚合。

        /stats 路由只需要聚合统计；走 list_usage_logs 全链路会白做一次
        items 查询。返回结构与 _empty_stats()/stats_dict 完全一致。
        """
        query = self._build_query(user_id=user_id, start_date=start_date)
        try:
            _, stats = await self._count_and_stats(query)
            return stats
        except AppError:
            # 入参校验错误（如非法日期格式）必须冒泡为 400
            raise
        except Exception as e:
            logger.error(f"Failed to aggregate usage stats (stats-only): {e}")
            raise

    def _build_query(
        self,
        *,
        user_id: Optional[str] = None,
        model: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}

        if user_id:
            query["user_id"] = user_id
        if model:
            query["model"] = model
        if start_date or end_date:
            date_filter: Dict[str, Any] = {}
            if start_date:
                date_filter["$gte"] = _parse_date_filter(start_date)
            if end_date:
                date_filter["$lt"] = _parse_date_filter(end_date)
            query["started_at"] = date_filter
        if search:
            query["username"] = {"$regex": search, "$options": "i"}
        return query

    async def get_usage_dashboard(
        self,
        *,
        user_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        model: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate usage logs into an operations dashboard."""
        query = self._build_query(
            user_id=user_id,
            model=model,
            start_date=start_date,
            end_date=end_date,
            search=search,
        )
        pipeline = [
            {"$match": query},
            {
                "$facet": {
                    "summary": [
                        {
                            "$group": {
                                "_id": None,
                                "total_requests": {"$sum": 1},
                                "total_tokens": _token_sum("total_tokens"),
                                "total_input_tokens": _token_sum("input_tokens"),
                                "total_output_tokens": _token_sum("output_tokens"),
                                "total_cache_read_tokens": _token_sum("cache_read_tokens"),
                                "total_cache_creation_tokens": _token_sum("cache_creation_tokens"),
                                "total_duration": {"$sum": "$duration"},
                                "total_tool_calls": {"$sum": "$tool_calls"},
                                "max_duration": {"$max": "$duration"},
                                "total_cost_usd": {
                                    "$sum": {"$cond": [PRICED_USAGE_CONDITION, "$cost_usd", 0]}
                                },
                                **_cost_certainty_aggregates(),
                                **_counter_availability_aggregates(),
                                "unpriced_requests": {
                                    "$sum": {"$cond": [PRICED_USAGE_CONDITION, 0, 1]}
                                },
                                "priced_requests": {
                                    "$sum": {"$cond": [PRICED_USAGE_CONDITION, 1, 0]}
                                },
                                "usage_unknown_requests": {
                                    "$sum": {"$cond": [COMPLETE_USAGE_CONDITION, 0, 1]}
                                },
                                "cache_unknown_requests": {
                                    "$sum": {"$cond": [CACHE_METRICS_CONDITION, 0, 1]}
                                },
                                "cache_uncertified_requests": {
                                    "$sum": {"$cond": [CERTIFIED_CACHE_METRICS_CONDITION, 0, 1]}
                                },
                                "scheduled_runs": {
                                    "$sum": {"$cond": [SCHEDULED_USAGE_CONDITION, 1, 0]}
                                },
                                "successful_requests": {
                                    "$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                                },
                                "cancelled_requests": {
                                    "$sum": {"$cond": [{"$eq": ["$status", "cancelled"]}, 1, 0]}
                                },
                                # 用户取消不算失败：failed 只统计 error 等真异常
                                "failed_requests": {
                                    "$sum": {
                                        "$cond": [
                                            {
                                                "$and": [
                                                    {"$ne": ["$status", "completed"]},
                                                    {"$ne": ["$status", "cancelled"]},
                                                    {"$ne": ["$status", "running"]},
                                                ]
                                            },
                                            1,
                                            0,
                                        ]
                                    }
                                },
                            }
                        }
                    ],
                    "daily": [
                        {
                            "$group": {
                                "_id": {
                                    "$dateToString": {
                                        "format": "%Y-%m-%d",
                                        "date": "$started_at",
                                    }
                                },
                                "requests": {"$sum": 1},
                                "tokens": _token_sum("total_tokens"),
                                "input_tokens": _token_sum("input_tokens"),
                                "cache_read_tokens": _token_sum("cache_read_tokens"),
                                "cache_creation_tokens": _token_sum("cache_creation_tokens"),
                                "duration": {"$sum": "$duration"},
                                "cost_usd": {
                                    "$sum": {"$cond": [PRICED_USAGE_CONDITION, "$cost_usd", 0]}
                                },
                                **_cost_certainty_aggregates(),
                                **_counter_availability_aggregates(),
                                "priced_requests": {
                                    "$sum": {"$cond": [PRICED_USAGE_CONDITION, 1, 0]}
                                },
                                "unpriced_requests": {
                                    "$sum": {"$cond": [PRICED_USAGE_CONDITION, 0, 1]}
                                },
                                "usage_unknown_requests": {
                                    "$sum": {"$cond": [COMPLETE_USAGE_CONDITION, 0, 1]}
                                },
                                "cache_unknown_requests": {
                                    "$sum": {"$cond": [CACHE_METRICS_CONDITION, 0, 1]}
                                },
                                "cache_uncertified_requests": {
                                    "$sum": {"$cond": [CERTIFIED_CACHE_METRICS_CONDITION, 0, 1]}
                                },
                                "scheduled_runs": {
                                    "$sum": {"$cond": [SCHEDULED_USAGE_CONDITION, 1, 0]}
                                },
                                "cancelled_requests": {
                                    "$sum": {"$cond": [{"$eq": ["$status", "cancelled"]}, 1, 0]}
                                },
                                "failed_requests": {
                                    "$sum": {
                                        "$cond": [
                                            {
                                                "$and": [
                                                    {"$ne": ["$status", "completed"]},
                                                    {"$ne": ["$status", "cancelled"]},
                                                    {"$ne": ["$status", "running"]},
                                                ]
                                            },
                                            1,
                                            0,
                                        ]
                                    }
                                },
                                "tool_calls": {"$sum": "$tool_calls"},
                            }
                        },
                        {"$sort": {"_id": 1}},
                    ],
                    "agents": self._ranking_pipeline("agent_name"),
                    "teams": self._ranking_pipeline("team_id", name_field="team_name"),
                    "personas": self._ranking_pipeline(
                        "persona_preset_id", name_field="persona_preset_name"
                    ),
                    "models": self._ranking_pipeline("model", include_cache_metrics=True),
                    "users": self._ranking_pipeline("user_id", name_field="username"),
                    "sources": self._ranking_pipeline(
                        "source",
                        fallback_id="chat",
                        include_empty=True,
                    ),
                    "triggers": self._ranking_pipeline("scheduled_task_trigger_type"),
                }
            },
        ]

        try:
            async for doc in await self.collection.aggregate(pipeline):
                return _format_dashboard(doc)
        except Exception as e:
            logger.error(f"Failed to aggregate usage dashboard: {e}")
            raise
        return _empty_dashboard()

    def _ranking_pipeline(
        self,
        field: str,
        *,
        name_field: str | None = None,
        limit: int = USAGE_RANKING_LIMIT,
        fallback_id: str | None = None,
        include_empty: bool = False,
        include_cache_metrics: bool = False,
    ) -> list[Dict[str, Any]]:
        group_id: Any = f"${field}"
        if fallback_id:
            group_id = {
                "$cond": [
                    {"$in": [f"${field}", [None, ""]]},
                    fallback_id,
                    f"${field}",
                ]
            }
        group: Dict[str, Any] = {
            "_id": group_id,
            "requests": {"$sum": 1},
            "tokens": _token_sum("total_tokens"),
            "input_tokens": _token_sum("input_tokens"),
            "cache_creation_tokens": _token_sum("cache_creation_tokens"),
            "cache_read_tokens": _token_sum("cache_read_tokens"),
            "duration": {"$sum": "$duration"},
            "cost_usd": {"$sum": {"$cond": [PRICED_USAGE_CONDITION, "$cost_usd", 0]}},
            **_cost_certainty_aggregates(),
            **_counter_availability_aggregates(),
            "priced_requests": {"$sum": {"$cond": [PRICED_USAGE_CONDITION, 1, 0]}},
            "unpriced_requests": {"$sum": {"$cond": [PRICED_USAGE_CONDITION, 0, 1]}},
            "usage_unknown_requests": {"$sum": {"$cond": [COMPLETE_USAGE_CONDITION, 0, 1]}},
            "cache_unknown_requests": {"$sum": {"$cond": [CACHE_METRICS_CONDITION, 0, 1]}},
            "cache_uncertified_requests": {
                "$sum": {"$cond": [CERTIFIED_CACHE_METRICS_CONDITION, 0, 1]}
            },
        }
        if name_field:
            group["name"] = {"$first": f"${name_field}"}
        if include_cache_metrics:
            group.update(
                {
                    "zero_cache_requests": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        CACHE_METRICS_CONDITION,
                                        {
                                            "$lte": [
                                                {"$ifNull": ["$cache_read_tokens", 0]},
                                                0,
                                            ]
                                        },
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                }
            )
        pipeline: list[Dict[str, Any]] = []
        if not include_empty:
            pipeline.append({"$match": {field: {"$nin": [None, ""]}}})
        pipeline.extend(
            [
                {"$group": group},
                {"$sort": {"tokens": -1, "requests": -1}},
                {"$limit": limit},
            ]
        )
        return pipeline

    async def _count_and_stats(self, query: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
        """计算总数和聚合统计"""
        total = await self.collection.count_documents(query)

        pipeline = [
            {"$match": query},
            {
                "$group": {
                    "_id": None,
                    "total_input_tokens": _token_sum("input_tokens"),
                    "total_output_tokens": _token_sum("output_tokens"),
                    "total_tokens": _token_sum("total_tokens"),
                    "total_cache_creation_tokens": _token_sum("cache_creation_tokens"),
                    "total_cache_read_tokens": _token_sum("cache_read_tokens"),
                    "total_duration": {"$sum": "$duration"},
                    "total_cost_usd": {"$sum": {"$cond": [PRICED_USAGE_CONDITION, "$cost_usd", 0]}},
                    **_cost_certainty_aggregates(),
                    **_counter_availability_aggregates(),
                    "unpriced_requests": {"$sum": {"$cond": [PRICED_USAGE_CONDITION, 0, 1]}},
                    "priced_requests": {"$sum": {"$cond": [PRICED_USAGE_CONDITION, 1, 0]}},
                    "usage_unknown_requests": {"$sum": {"$cond": [COMPLETE_USAGE_CONDITION, 0, 1]}},
                    "cache_unknown_requests": {"$sum": {"$cond": [CACHE_METRICS_CONDITION, 0, 1]}},
                    "cache_uncertified_requests": {
                        "$sum": {"$cond": [CERTIFIED_CACHE_METRICS_CONDITION, 0, 1]}
                    },
                }
            },
        ]

        stats = _empty_stats()
        stats["total_requests"] = total

        try:
            async for doc in await self.collection.aggregate(pipeline):
                stats.update(
                    {
                        "total_input_tokens": doc.get("total_input_tokens", 0),
                        "total_output_tokens": doc.get("total_output_tokens", 0),
                        "total_tokens": doc.get("total_tokens", 0),
                        "total_cache_creation_tokens": doc.get("total_cache_creation_tokens", 0),
                        "total_cache_read_tokens": doc.get("total_cache_read_tokens", 0),
                        "total_duration": doc.get("total_duration", 0.0),
                        "total_cost_usd": doc.get("total_cost_usd", 0.0),
                        **_format_cost_certainty(doc),
                        **_format_counter_availability(doc),
                        "unpriced_requests": doc.get("unpriced_requests", 0),
                        "priced_requests": doc.get("priced_requests", 0),
                        "usage_unknown_requests": doc.get("usage_unknown_requests", 0),
                        "cache_unknown_requests": _aggregate_cache_unknown_requests(
                            doc, "total_cache_read_tokens"
                        ),
                    }
                )
                break  # only one group result
        except Exception as e:
            logger.error(f"Failed to aggregate usage stats: {e}")
            raise

        return total, stats

    async def _fetch_items(
        self, query: Dict[str, Any], skip: int, limit: int
    ) -> List[Dict[str, Any]]:
        """获取分页数据"""
        try:
            cursor = (
                self.collection.find(query, {"_id": 0})
                .sort("started_at", -1)
                .skip(skip)
                .limit(limit)
            )
            items = await cursor.to_list(length=limit)
            for item in items:
                item.update(_usage_cost_fields(item))
                incomplete = item.get("usage_incomplete")
                item["usage_incomplete"] = incomplete if isinstance(incomplete, bool) else None
            return items
        except Exception as e:
            logger.error(f"Failed to fetch usage items: {e}")
            raise

    async def list_unpriced_usage_logs(
        self, *, limit: int = 500, exclude_trace_ids: set[str] | None = None
    ) -> List[Dict[str, Any]]:
        """读取未计价（cost_available != True）的记录，按时间升序分批。

        回填用：已回填的记录不再命中查询，重复执行天然幂等。
        """
        try:
            query: Dict[str, Any] = {
                "cost_available": {"$ne": True},
                "cost_source": {"$ne": "provider_settlement"},
            }
            if exclude_trace_ids:
                query["trace_id"] = {"$nin": list(exclude_trace_ids)}
            cursor = self.collection.find(query, {"_id": 0}).sort("started_at", 1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Failed to list unpriced usage logs: {e}")
            raise

    async def update_usage_cost(
        self,
        trace_id: str,
        cost_usd: float,
        *,
        expected_usage: Dict[str, Any] | None = None,
        cost_complete: bool = False,
        cost_rates: Dict[str, Any] | None = None,
    ) -> bool:
        """回填单条记录的 USD 费用快照。"""
        if not _valid_cost(cost_usd):
            return False
        if (expected_usage or {}).get("cost_source") == "provider_settlement":
            return False
        try:
            query: dict[str, Any] = {
                "trace_id": trace_id,
                "cost_source": {"$ne": "provider_settlement"},
                "cost_available": {"$ne": True},
                "usage_incomplete": {"$eq": False, "$type": "bool"},
                "input_includes_cache": {"$eq": True, "$type": "bool"},
            }
            if expected_usage is not None:
                for key in (
                    "input_tokens",
                    "output_tokens",
                    "cache_read_tokens",
                    "cache_creation_tokens",
                ):
                    query[key] = expected_usage.get(key)
                query["model"] = expected_usage.get("model")
                query["model_id"] = expected_usage.get("model_id")
            values: Dict[str, Any] = {"cost_usd": cost_usd, "cost_available": True}
            if cost_complete is True:
                if expected_usage is None or expected_usage.get("cost_available") is True:
                    return False
                classified = _usage_cost_fields(
                    {
                        **expected_usage,
                        **values,
                        "cost_complete": True,
                        "cost_rates": cost_rates,
                    }
                )
                if not classified["cost_complete"] or not classified["cost_available"]:
                    return False
                query = _usage_snapshot_query(trace_id, expected_usage)
                values.update(cost_complete=True, cost_rates=cost_rates)
            result = await self.collection.update_one(
                query,
                {"$set": values},
            )
            return bool(result.matched_count)
        except Exception as e:
            logger.error(f"Failed to update usage cost for trace {trace_id}: {e}")
            return False

    async def update_usage_partial_cost(
        self, trace_id: str, cost_usd: float, *, expected_usage: Dict[str, Any]
    ) -> bool:
        """Write only independent cost components while the original usage snapshot still matches."""
        if (
            expected_usage.get("cost_source") == "provider_settlement"
            or expected_usage.get("input_includes_cache") is not True
            or not _valid_cost(cost_usd)
        ):
            return False
        query = _usage_snapshot_query(trace_id, expected_usage)
        try:
            result = await self.collection.update_one(
                query, {"$set": {"partial_cost_usd": cost_usd}}
            )
            return bool(result.matched_count)
        except Exception as error:
            logger.error("Failed to update partial cost for trace %s: %s", trace_id, error)
            return False

    async def get_user_usage_summary(self, user_id: str) -> Dict[str, Any]:
        """获取单个用户的用量汇总"""
        query = {"user_id": user_id}
        total = await self.collection.count_documents(query)

        pipeline = [
            {"$match": query},
            {
                "$group": {
                    "_id": None,
                    "total_input_tokens": _token_sum("input_tokens"),
                    "total_output_tokens": _token_sum("output_tokens"),
                    "total_tokens": _token_sum("total_tokens"),
                    "total_duration": {"$sum": "$duration"},
                    "total_cost_usd": {"$sum": {"$cond": [PRICED_USAGE_CONDITION, "$cost_usd", 0]}},
                    **_cost_certainty_aggregates(),
                    **_counter_availability_aggregates(),
                }
            },
        ]

        summary: Dict[str, Any] = {
            "total_requests": total,
            "total_cost_usd": 0.0,
            **_format_cost_certainty({}),
            **_format_counter_availability({}),
        }
        try:
            async for doc in await self.collection.aggregate(pipeline):
                summary.update(
                    {
                        "total_input_tokens": doc.get("total_input_tokens", 0),
                        "total_output_tokens": doc.get("total_output_tokens", 0),
                        "total_tokens": doc.get("total_tokens", 0),
                        "total_duration": doc.get("total_duration", 0.0),
                        "total_cost_usd": doc.get("total_cost_usd", 0.0),
                        **_format_cost_certainty(doc),
                        **_format_counter_availability(doc),
                    }
                )
                break
        except Exception as e:
            logger.error(f"Failed to get user usage summary: {e}")

        return summary


def get_usage_storage() -> UsageStorage:
    """获取 UsageStorage 实例"""
    return UsageStorage()
