"""
Usage storage layer.

独立的 usage_logs 集合，在 trace 完成时写入扁平化的 token 消耗记录。
查询时直接从该集合读取，避免对 traces 集合做复杂聚合。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.infra.logging import get_logger
from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import parse_iso
from src.kernel.config import settings

logger = get_logger(__name__)

USAGE_LOG_LIMIT_MAX = 200
USAGE_RANKING_LIMIT = 8
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


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(float(value)), 0)
        except ValueError:
            return 0
    return 0


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return max(float(value), 0.0)
    if isinstance(value, str):
        try:
            return max(float(value), 0.0)
        except ValueError:
            return 0.0
    return 0.0


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
        for event in reversed(trace_doc.get("events", [])):
            if event.get("event_type") == "token:usage":
                usage_event = event.get("data", {})
                break

        return await self.upsert_usage_log_from_trace_metadata(trace_doc, usage_event)

    async def upsert_usage_log_from_trace_metadata(
        self,
        trace_doc: Dict[str, Any],
        usage_data: Optional[Dict[str, Any]],
    ) -> bool:
        """
        使用 trace 元数据和已解析的 token:usage 数据写入 usage_logs。

        Args:
            trace_doc: trace 元数据（不需要包含完整 events）
            usage_data: 最后一条 token:usage 事件的 data；缺失时按 0 处理

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

        doc = {
            "trace_id": trace_id,
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
            "model": usage_data.get("model", ""),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cache_creation_tokens": _as_int(usage_data.get("cache_creation_tokens", 0)),
            "cache_read_tokens": _as_int(usage_data.get("cache_read_tokens", 0)),
            "duration": _as_float(usage_data.get("duration", 0.0)),
            "started_at": _as_datetime(trace_doc.get("started_at")),
            "completed_at": _as_datetime(trace_doc.get("completed_at")),
            "status": trace_doc.get("status", "unknown"),
            "step_count": _as_int(metadata.get("step_count", 0)),
            "tool_calls": _as_int(metadata.get("tool_calls", 0)),
        }

        try:
            await self.collection.update_one(
                {"trace_id": trace_id},
                {"$set": doc},
                upsert=True,
            )
            return True
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

            count_task = asyncio.create_task(self._count_and_stats(query))
            items_task = asyncio.create_task(self._fetch_items(query, skip, limit))

            total, stats = await count_task
            items = await items_task

            return items, total, stats
        except Exception as e:
            logger.error(f"Failed to list usage logs: {e}")
            return [], 0, _empty_stats()

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
                date_filter["$gte"] = parse_iso(start_date)
            if end_date:
                date_filter["$lt"] = parse_iso(end_date)
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
                                "total_tokens": {"$sum": "$total_tokens"},
                                "total_input_tokens": {"$sum": "$input_tokens"},
                                "total_output_tokens": {"$sum": "$output_tokens"},
                                "total_cache_read_tokens": {"$sum": "$cache_read_tokens"},
                                "total_duration": {"$sum": "$duration"},
                                "total_tool_calls": {"$sum": "$tool_calls"},
                                "max_duration": {"$max": "$duration"},
                                "scheduled_runs": {
                                    "$sum": {"$cond": [SCHEDULED_USAGE_CONDITION, 1, 0]}
                                },
                                "successful_requests": {
                                    "$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                                },
                                "failed_requests": {
                                    "$sum": {"$cond": [{"$ne": ["$status", "completed"]}, 1, 0]}
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
                                "tokens": {"$sum": "$total_tokens"},
                                "duration": {"$sum": "$duration"},
                                "scheduled_runs": {
                                    "$sum": {"$cond": [SCHEDULED_USAGE_CONDITION, 1, 0]}
                                },
                                "failed_requests": {
                                    "$sum": {"$cond": [{"$ne": ["$status", "completed"]}, 1, 0]}
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
                    "models": self._ranking_pipeline("model"),
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
            async for doc in self.collection.aggregate(pipeline):
                return _format_dashboard(doc)
        except Exception as e:
            logger.error(f"Failed to aggregate usage dashboard: {e}")
        return _empty_dashboard()

    def _ranking_pipeline(
        self,
        field: str,
        *,
        name_field: str | None = None,
        limit: int = USAGE_RANKING_LIMIT,
        fallback_id: str | None = None,
        include_empty: bool = False,
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
            "tokens": {"$sum": "$total_tokens"},
            "duration": {"$sum": "$duration"},
        }
        if name_field:
            group["name"] = {"$first": f"${name_field}"}
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
                    "total_input_tokens": {"$sum": "$input_tokens"},
                    "total_output_tokens": {"$sum": "$output_tokens"},
                    "total_tokens": {"$sum": "$total_tokens"},
                    "total_cache_creation_tokens": {"$sum": "$cache_creation_tokens"},
                    "total_cache_read_tokens": {"$sum": "$cache_read_tokens"},
                    "total_duration": {"$sum": "$duration"},
                }
            },
        ]

        stats = _empty_stats()
        stats["total_requests"] = total

        try:
            async for doc in self.collection.aggregate(pipeline):
                stats.update(
                    {
                        "total_input_tokens": doc.get("total_input_tokens", 0),
                        "total_output_tokens": doc.get("total_output_tokens", 0),
                        "total_tokens": doc.get("total_tokens", 0),
                        "total_cache_creation_tokens": doc.get("total_cache_creation_tokens", 0),
                        "total_cache_read_tokens": doc.get("total_cache_read_tokens", 0),
                        "total_duration": doc.get("total_duration", 0.0),
                    }
                )
                break  # only one group result
        except Exception as e:
            logger.error(f"Failed to aggregate usage stats: {e}")

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
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Failed to fetch usage items: {e}")
            return []

    async def get_user_usage_summary(self, user_id: str) -> Dict[str, Any]:
        """获取单个用户的用量汇总"""
        query = {"user_id": user_id}
        total = await self.collection.count_documents(query)

        pipeline = [
            {"$match": query},
            {
                "$group": {
                    "_id": None,
                    "total_input_tokens": {"$sum": "$input_tokens"},
                    "total_output_tokens": {"$sum": "$output_tokens"},
                    "total_tokens": {"$sum": "$total_tokens"},
                    "total_duration": {"$sum": "$duration"},
                }
            },
        ]

        summary: Dict[str, Any] = {"total_requests": total}
        try:
            async for doc in self.collection.aggregate(pipeline):
                summary.update(
                    {
                        "total_input_tokens": doc.get("total_input_tokens", 0),
                        "total_output_tokens": doc.get("total_output_tokens", 0),
                        "total_tokens": doc.get("total_tokens", 0),
                        "total_duration": doc.get("total_duration", 0.0),
                    }
                )
                break
        except Exception as e:
            logger.error(f"Failed to get user usage summary: {e}")

        return summary


def _empty_stats() -> Dict[str, Any]:
    return {
        "total_requests": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "total_cache_creation_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_duration": 0.0,
    }


def _format_ranking_item(doc: Dict[str, Any]) -> Dict[str, Any]:
    item_id = str(doc.get("_id") or "")
    return {
        "id": item_id,
        "name": str(doc.get("name") or item_id or "Unknown"),
        "requests": _as_int(doc.get("requests")),
        "tokens": _as_int(doc.get("tokens")),
        "duration": _as_float(doc.get("duration")),
    }


def _format_dashboard(doc: Dict[str, Any]) -> Dict[str, Any]:
    summary_doc = (doc.get("summary") or [{}])[0] if isinstance(doc.get("summary"), list) else {}
    total_requests = _as_int(summary_doc.get("total_requests"))
    successful_requests = _as_int(summary_doc.get("successful_requests"))
    total_tokens = _as_int(summary_doc.get("total_tokens"))
    total_input_tokens = _as_int(summary_doc.get("total_input_tokens"))
    total_cache_read_tokens = _as_int(summary_doc.get("total_cache_read_tokens"))
    total_duration = _as_float(summary_doc.get("total_duration"))
    scheduled_runs = _as_int(summary_doc.get("scheduled_runs"))
    total_tool_calls = _as_int(summary_doc.get("total_tool_calls"))
    failed_requests = _as_int(summary_doc.get("failed_requests"))
    daily_items = [
        {
            "date": str(item.get("_id") or ""),
            "requests": _as_int(item.get("requests")),
            "tokens": _as_int(item.get("tokens")),
            "duration": _as_float(item.get("duration")),
            "scheduled_runs": _as_int(item.get("scheduled_runs")),
            "failed_requests": _as_int(item.get("failed_requests")),
            "tool_calls": _as_int(item.get("tool_calls")),
        }
        for item in doc.get("daily", [])
        if item.get("_id")
    ]
    peak_day = max(
        daily_items,
        key=lambda item: (item["tokens"], item["requests"], item["duration"]),
        default=None,
    )
    summary = {
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": _as_int(summary_doc.get("total_output_tokens")),
        "total_cache_read_tokens": total_cache_read_tokens,
        "total_duration": total_duration,
        "total_tool_calls": total_tool_calls,
        "scheduled_runs": scheduled_runs,
        "failed_requests": failed_requests,
        "success_rate": (successful_requests / total_requests) if total_requests else 0.0,
        "avg_tokens_per_request": (total_tokens / total_requests) if total_requests else 0.0,
        "avg_duration_per_request": (total_duration / total_requests) if total_requests else 0.0,
        "scheduled_share": (scheduled_runs / total_requests) if total_requests else 0.0,
        "cache_read_share": (
            (total_cache_read_tokens / total_input_tokens) if total_input_tokens else 0.0
        ),
        "tool_calls_per_request": ((total_tool_calls / total_requests) if total_requests else 0.0),
        "max_duration": _as_float(summary_doc.get("max_duration")),
        "peak_day": peak_day,
    }
    return {
        "summary": summary,
        "daily": daily_items,
        "top_agents": [_format_ranking_item(item) for item in doc.get("agents", [])],
        "top_teams": [_format_ranking_item(item) for item in doc.get("teams", [])],
        "top_personas": [_format_ranking_item(item) for item in doc.get("personas", [])],
        "top_models": [_format_ranking_item(item) for item in doc.get("models", [])],
        "top_users": [_format_ranking_item(item) for item in doc.get("users", [])],
        "sources": [_format_ranking_item(item) for item in doc.get("sources", [])],
        "triggers": [_format_ranking_item(item) for item in doc.get("triggers", [])],
    }


def _empty_dashboard() -> Dict[str, Any]:
    return {
        "summary": {
            "total_requests": 0,
            "total_tokens": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_read_tokens": 0,
            "total_duration": 0.0,
            "total_tool_calls": 0,
            "scheduled_runs": 0,
            "failed_requests": 0,
            "success_rate": 0.0,
            "avg_tokens_per_request": 0.0,
            "avg_duration_per_request": 0.0,
            "scheduled_share": 0.0,
            "cache_read_share": 0.0,
            "tool_calls_per_request": 0.0,
            "max_duration": 0.0,
            "peak_day": None,
        },
        "daily": [],
        "top_agents": [],
        "top_teams": [],
        "top_personas": [],
        "top_models": [],
        "top_users": [],
        "sources": [],
        "triggers": [],
    }


def get_usage_storage() -> UsageStorage:
    """获取 UsageStorage 实例"""
    return UsageStorage()
