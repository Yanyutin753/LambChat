"""
Usage log schemas for token consumption tracking.

定义使用日志的数据模型，基于 traces 集合中的 token:usage 事件。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UsageLog(BaseModel):
    """单条使用日志（一次 trace 的 token 消耗）"""

    trace_id: str
    session_id: str
    user_id: str
    username: str = ""
    agent_name: str = ""
    team_id: str = ""
    team_name: str = ""
    persona_preset_id: str = ""
    persona_preset_name: str = ""
    source: str = "chat"
    scheduled_task_id: str = ""
    scheduled_task_run_id: str = ""
    scheduled_task_trigger_type: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    duration: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "unknown"
    error_message: str = ""
    error_type: str = ""

    model_config = ConfigDict(from_attributes=True)


class UsageStats(BaseModel):
    """聚合使用统计"""

    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_duration: float = 0.0


class UsageLogListResponse(BaseModel):
    """分页使用日志列表响应"""

    items: list[UsageLog]
    total: int
    stats: UsageStats


class UsageDashboardSummary(BaseModel):
    total_requests: int = 0
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_duration: float = 0.0
    total_tool_calls: int = 0
    scheduled_runs: int = 0
    failed_requests: int = 0
    success_rate: float = 0.0
    avg_tokens_per_request: float = 0.0
    avg_duration_per_request: float = 0.0
    scheduled_share: float = 0.0
    cache_read_share: float = 0.0
    tool_calls_per_request: float = 0.0
    max_duration: float = 0.0
    peak_day: Optional["UsageDailyPoint"] = None


class UsageDailyPoint(BaseModel):
    date: str
    requests: int = 0
    tokens: int = 0
    duration: float = 0.0
    scheduled_runs: int = 0
    failed_requests: int = 0
    tool_calls: int = 0


class UsageRankingItem(BaseModel):
    id: str
    name: str
    requests: int = 0
    tokens: int = 0
    duration: float = 0.0
    input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cache_read_share: float = 0.0
    zero_cache_requests: int = 0


class UsageDashboardResponse(BaseModel):
    summary: UsageDashboardSummary
    daily: list[UsageDailyPoint]
    top_agents: list[UsageRankingItem]
    top_teams: list[UsageRankingItem]
    top_personas: list[UsageRankingItem]
    top_models: list[UsageRankingItem]
    top_users: list[UsageRankingItem] = []
    sources: list[UsageRankingItem] = []
    triggers: list[UsageRankingItem] = []
