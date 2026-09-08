from __future__ import annotations

"""arq 取任务轮询间隔设置：缩短派发拾取延迟（HITL resume 提速）。"""

from src.kernel.config.base import Settings
from src.kernel.config.definitions import SETTING_DEFINITIONS


def test_arq_poll_delay_definition_exists() -> None:
    definition = SETTING_DEFINITIONS["ARQ_POLL_DELAY_SECONDS"]
    assert definition["category"].value == "redis"
    assert definition["subcategory"] == "task"
    assert definition["frontend_visible"] is False


def test_arq_poll_delay_defaults_match_settings_field() -> None:
    assert Settings().ARQ_POLL_DELAY_SECONDS == 0.1
    assert SETTING_DEFINITIONS["ARQ_POLL_DELAY_SECONDS"]["default"] == 0.1
