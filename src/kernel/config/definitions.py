"""Setting metadata definitions - single source of truth.

This module assembles SETTING_DEFINITIONS from domain-grouped sub-modules:
  - _definitions_core: Frontend, Application, LLM, Session, Event Merger
  - _definitions_sandbox: Sandbox platform, Skills, Code Interpreter
  - _definitions_tools: MCP, Audio, Image Analysis, Image Generation, Scheduled Task
  - _definitions_infra: MongoDB, Redis, Task Backend, LangSmith Tracing
  - _definitions_extra: Security, Storage, User, Memory (already existed)
"""

from __future__ import annotations

from src.kernel.config._definitions_core import CORE_SETTING_DEFINITIONS
from src.kernel.config._definitions_extra import EXTRA_SETTING_DEFINITIONS
from src.kernel.config._definitions_infra import INFRA_SETTING_DEFINITIONS
from src.kernel.config._definitions_sandbox import SANDBOX_SETTING_DEFINITIONS
from src.kernel.config._definitions_tools import TOOLS_SETTING_DEFINITIONS
from src.kernel.schemas.setting import SettingCategory, SettingType

# Re-export for convenience
__all__ = ["SETTING_DEFINITIONS", "SettingCategory", "SettingType"]

# Assemble all definitions
SETTING_DEFINITIONS: dict[str, dict] = {
    **CORE_SETTING_DEFINITIONS,
    **SANDBOX_SETTING_DEFINITIONS,
    **TOOLS_SETTING_DEFINITIONS,
    **INFRA_SETTING_DEFINITIONS,
    **EXTRA_SETTING_DEFINITIONS,
}
