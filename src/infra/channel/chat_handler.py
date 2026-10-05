"""Provider-independent text chat execution with tenant-scoped sessions."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from src.infra.channel.channel_storage import ChannelStorage
from src.infra.channel.recovery import delivery_session, read_channel_events, submit_channel_task
from src.infra.channel.session_scope import new_delivery_session
from src.infra.storage.redis import RedisStorage


def session_scope(channel: Any, sender_id: str, chat_id: str, metadata: dict) -> str:
    identity = [
        channel.channel_type.value,
        channel.user_id,
        channel.config.instance_id,
        chat_id,
        sender_id,
        metadata.get("thread_ts", ""),
        metadata.get("message_thread_id", ""),
    ]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


async def execute_chat_agent(
    session_id: str,
    agent_id: str,
    message: str,
    user_id: str,
    presenter=None,
    disabled_tools=None,
    agent_options=None,
    attachments=None,
    disabled_skills=None,
    enabled_skills=None,
    persona_system_prompt=None,
    disabled_mcp_tools=None,
    enabled_mcp_servers=None,
    hitl_resume=None,
    base_url="",
    recommendation_input=None,
    team_id=None,
    active_goal=None,
    auto_mode=False,
):
    from src.agents.core.base import AgentFactory

    agent = await AgentFactory.get(agent_id)
    async for event in agent.stream(
        message,
        session_id,
        user_id=user_id,
        presenter=presenter,
        agent_options=agent_options,
        persona_system_prompt=persona_system_prompt,
        enabled_skills=enabled_skills,
        disabled_tools=disabled_tools,
        disabled_skills=disabled_skills,
        disabled_mcp_tools=disabled_mcp_tools,
        enabled_mcp_servers=enabled_mcp_servers,
        hitl_resume=hitl_resume,
        base_url=base_url,
        attachments=attachments,
        recommendation_input=recommendation_input,
        team_id=team_id,
        active_goal=active_goal,
        auto_mode=auto_mode,
    ):
        yield event


def create_chat_message_handler(channel: Any, default_agent: str):
    async def handle(*, user_id: str, sender_id: str, chat_id: str, content: str, metadata: dict):
        from src.infra.session.manager import SessionManager
        from src.infra.task.manager import get_task_manager

        config = await ChannelStorage().get_config(
            channel.user_id, channel.channel_type, channel.config.instance_id
        )
        # A deletion/disable during an in-flight callback must not launch a run.
        if (
            not config
            or not config.get("enabled", True)
            or not config.get("receive_enabled", channel.config.receive_enabled)
        ):
            return
        current_config = channel.config.model_copy(
            update={
                key: config.get(key, "")
                for key in ("allowed_sender_ids", "allowed_chat_ids", "default_chat_id")
            }
        )
        if not channel._authorized({"sender_id": sender_id, "chat_id": chat_id}, current_config):
            return
        scope = session_scope(channel, sender_id, chat_id, metadata)
        redis = RedisStorage()
        key = f"channel:session:{scope}"
        if content.strip() == "/new":
            await redis.set(key, await new_delivery_session(f"channel_{scope}"))
            if not await channel.send_message(chat_id, "New conversation ready.", **metadata):
                raise RuntimeError("Channel reply failed")
            return
        session_id = delivery_session(await redis.get(key) or f"channel_{scope}")
        from src.infra.channel.runtime import (
            build_channel_agent_options,
            build_channel_session_metadata,
        )

        agent_options = await build_channel_agent_options(config, channel.user_id)
        persona_system_prompt = None
        enabled_skills = None
        enabled_mcp_servers = None
        if config.get("persona_preset_id"):
            from src.infra.persona_preset.manager import PersonaPresetManager

            snapshot = await PersonaPresetManager().use_preset(
                config["persona_preset_id"], user_id=channel.user_id, is_admin=False
            )
            persona_system_prompt = snapshot.system_prompt
            enabled_skills = snapshot.skill_names or None
            enabled_mcp_servers = getattr(snapshot, "mcp_server_names", None) or None
        run_id, _ = await submit_channel_task(
            get_task_manager(),
            channel_delivery={
                "channel_type": channel.channel_type.value,
                "channel_instance_id": channel.config.instance_id,
                "chat_id": chat_id,
                "enabled": True,
                "send_on_success": True,
            },
            session_id=session_id,
            agent_id=config.get("agent_id") or default_agent,
            message=content,
            user_id=channel.user_id,
            executor=execute_chat_agent,
            agent_options=agent_options,
            project_id=config.get("project_id"),
            team_id=config.get("team_id"),
            persona_system_prompt=persona_system_prompt,
            enabled_skills=enabled_skills,
            auto_mode=False,
            enabled_mcp_servers=enabled_mcp_servers,
            session_metadata=build_channel_session_metadata(
                agent_id=config.get("agent_id") or default_agent,
                agent_options=agent_options,
                project_id=config.get("project_id"),
                team_id=config.get("team_id"),
                enabled_skills=enabled_skills,
                enabled_mcp_servers=enabled_mcp_servers,
                persona_system_prompt=persona_system_prompt,
                auto_mode=False,
            ),
        )
        try:
            await SessionManager().update_session_metadata(
                session_id,
                {
                    "channel_delivery": {
                        "channel_type": channel.channel_type.value,
                        "channel_instance_id": channel.config.instance_id,
                        "chat_id": chat_id,
                        "enabled": True,
                        "send_on_success": True,
                    }
                },
            )
            chunks: list[str] = []
            async for event in read_channel_events(session_id, run_id):
                kind = event.get("event_type")
                data = event.get("data")
                if not isinstance(data, dict):
                    continue
                if kind == "message:chunk" and isinstance(data.get("content"), str):
                    if str(data.get("depth") or 0) == "0" and data.get("role") not in (
                        "user",
                        "human",
                    ):
                        chunks.append(data["content"])
                elif kind == "run:resumed":
                    chunks.clear()
                elif kind == "approval_required":
                    await channel.send_message(
                        chat_id,
                        "Approval required. Open this conversation in LambChat to continue.",
                        **metadata,
                    )
                elif kind in ("done", "complete", "error"):
                    if kind == "error":
                        await channel.send_message(
                            chat_id,
                            "The agent could not complete this request. Check the conversation in LambChat.",
                            **metadata,
                        )
                    break
            reply = "".join(chunks).strip()
            if reply and not await channel.send_message(chat_id, reply, **metadata):
                raise RuntimeError("Channel reply failed")
        except asyncio.CancelledError:
            # Transport shutdown detaches the reply reader; task recovery owns the run.
            raise

    return handle
