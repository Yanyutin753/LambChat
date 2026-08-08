"""Skill collection index initialization.

Split from storage.py to keep that module under the repo's 1000-line cap.
"""

from typing import Any


async def ensure_skill_indexes(storage: Any) -> None:
    """创建索引"""
    files = storage._get_files_collection()
    await files.create_index(
        [("skill_name", 1), ("user_id", 1), ("file_path", 1)], unique=True, background=True
    )
    # P1-6: {user_id, file_path} 查询缺 skill_name，无法用上面的唯一索引；
    # 非唯一（同 user 跨 skill 共享 file_path 如 SKILL.md）。
    await files.create_index(
        [("user_id", 1), ("file_path", 1)], name="user_file_path_idx", background=True
    )
