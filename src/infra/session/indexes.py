"""MongoDB session indexes shared by storage initialization."""

from typing import Any

# 会话集合索引清单（单一定义点）：(keys, name, 额外 kwargs)
SESSION_INDEX_SPEC: list[tuple[list[tuple[str, int]], str, dict[str, Any]]] = [
    # 列表排序 (is_pinned desc, updated_at desc)：等值前缀 + 排序后缀，避免大列表内存排序
    (
        [("user_id", 1), ("is_active", 1), ("metadata.is_pinned", -1), ("updated_at", -1)],
        "user_status_pinned_updated_idx",
        {},
    ),
    ([("user_id", 1), ("is_active", 1), ("updated_at", -1)], "user_status_updated_idx", {}),
    (
        [("user_id", 1), ("metadata.project_id", 1), ("updated_at", -1)],
        "user_project_updated_idx",
        {},
    ),
    (
        [("user_id", 1), ("metadata.project_id", 1), ("updated_at", -1), ("_id", -1)],
        "user_project_updated_id_idx",
        {},
    ),
    (
        [("user_id", 1), ("metadata.assistant_id", 1), ("updated_at", -1)],
        "user_assistant_updated_idx",
        {},
    ),
    (
        [("user_id", 1), ("metadata.background_assistant_id", 1), ("updated_at", -1)],
        "user_background_assistant_updated_idx",
        {},
    ),
    ([("session_id", 1)], "session_id_idx", {"sparse": True}),
    (
        [("user_id", 1), ("search_terms", 1), ("updated_at", -1)],
        "user_search_terms_updated_idx",
        {},
    ),
    ([("search_index_version", 1), ("updated_at", -1)], "search_index_version_updated_idx", {}),
    ([("search_index_updated_at", 1)], "search_index_updated_at_idx", {"sparse": True}),
    (
        [("metadata.scheduled_task_id", 1), ("updated_at", -1)],
        "scheduled_task_sessions_idx",
        {"sparse": True},
    ),
]
