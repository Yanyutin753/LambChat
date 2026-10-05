"""Validated channel execution options; environment values stay in encrypted storage."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ChannelRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, strict=True)

    sandbox: Literal["default", "local", "cloud"] = "default"
    sandbox_machine_id: str = Field(default="", max_length=256)
    enable_thinking: Literal["", "low", "medium", "high", "max"] = ""
    enable_code_interpreter: bool | None = None
    response_language: Literal["", "en", "zh", "ja", "ko", "ru"] = ""
    env_vars: dict[str, str] = Field(default_factory=dict)

    @field_validator("env_vars")
    @classmethod
    def validate_env_vars(cls, values: dict[str, str]) -> dict[str, str]:
        if len(values) > 50 or sum(len(value) for value in values.values()) > 64000:
            raise ValueError("Environment variable limit exceeded")
        for key, value in values.items():
            if (
                not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,255}", key)
                or key in {"LAMBCHAT_WORKSPACE", "LAMBCHAT_SHARED"}
                or len(value) > 16000
                or "\x00" in value
            ):
                raise ValueError("Invalid environment variable")
        return values


def normalize_runtime_config(value: Any, existing: dict | None = None) -> dict[str, Any]:
    """Partial settings update; env map replaces keys, with per-key masked-value retention."""
    if value is None:
        return ChannelRuntimeConfig().model_dump(exclude_none=True)
    if not isinstance(value, dict):
        raise ValueError("Invalid channel runtime configuration")
    merged = {**(existing or {}), **value}
    env_vars = merged.get("env_vars", {})
    if isinstance(env_vars, dict):
        env_vars = dict(env_vars)
        for key, env_value in env_vars.items():
            if env_value == "***":
                previous = (existing or {}).get("env_vars", {})
                if key not in previous:
                    raise ValueError("Unknown masked environment variable")
                env_vars[key] = previous[key]
        merged["env_vars"] = env_vars
    try:
        return ChannelRuntimeConfig.model_validate(merged).model_dump(exclude_none=True)
    except (ValidationError, TypeError, ValueError):
        raise ValueError("Invalid channel runtime configuration") from None


def mask_runtime_config(value: dict | None) -> dict:
    value = value or {}
    return {**value, "env_vars": {key: "***" for key in value.get("env_vars", {})}}


async def build_channel_agent_options(config: dict, user_id: str) -> dict[str, Any] | None:
    """Build non-secret options, resolving a project's machine and workspace on the server."""
    runtime = ChannelRuntimeConfig.model_validate(config.get("runtime_config") or {})
    options: dict[str, Any] = {}
    if runtime.sandbox != "default":
        options["sandbox"] = runtime.sandbox
    if runtime.sandbox == "local" and runtime.sandbox_machine_id:
        options["sandbox_machine_id"] = runtime.sandbox_machine_id
    for key in ("enable_thinking", "response_language"):
        if value := getattr(runtime, key):
            options[key] = value
    if runtime.enable_code_interpreter is not None:
        options["enable_code_interpreter"] = runtime.enable_code_interpreter
    if config.get("model_id"):
        options["model_id"] = config["model_id"]
    if runtime.env_vars:
        if not config.get("channel_type") or not config.get("instance_id"):
            raise ValueError("Channel runtime identity missing")
        options["channel_runtime"] = {
            "channel_type": config["channel_type"],
            "instance_id": config["instance_id"],
        }
    if config.get("project_id"):
        from src.infra.folder.storage import get_project_storage

        project = await get_project_storage().get_by_id(config["project_id"], user_id)
        if project is None:
            raise ValueError("Channel project is no longer available")
        project_workspace = getattr(project, "workspace", None)
        if project_workspace is not None:
            workspace = project_workspace.model_dump(by_alias=True)
            options.update(
                sandbox="local",
                sandbox_machine_id=workspace["machineId"],
                sandbox_workspace=json.dumps(workspace),
            )
    return options or None


def build_channel_session_metadata(
    *,
    agent_id: str,
    agent_options: dict | None,
    project_id: str | None,
    team_id: str | None,
    enabled_skills: list[str] | None,
    enabled_mcp_servers: list[str] | None,
    persona_system_prompt: str | None,
    auto_mode: bool,
) -> dict[str, Any]:
    """Persist a recoverable execution snapshot before starting or resuming a task."""
    return {
        "agent_id": agent_id,
        "executor_key": "agent_stream",
        "agent_options": agent_options or {},
        "project_id": project_id,
        "team_id": team_id,
        "enabled_skills": enabled_skills,
        "enabled_mcp_servers": enabled_mcp_servers,
        "persona_snapshot": {"system_prompt": persona_system_prompt}
        if persona_system_prompt
        else None,
        "auto_mode": auto_mode,
    }
