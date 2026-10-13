"""Conversation controls for TeamAgent's persistent subagents."""

import json

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.types import Command


def create_subagent_parent_tools(sessions, subagent_id: str):
    @tool
    async def send_parent_message(message: str, runtime: ToolRuntime) -> dict:
        """Send progress, evidence or a question to your parent agent's mailbox.
        Delivery is queued and returns immediately. A running parent receives it
        at its next execution boundary; an idle parent is not restarted.
        This does not pause your work or replace your final report."""
        return await sessions.send_parent(
            subagent_id,
            message,
            message_id=f"parent-message-{subagent_id}-{runtime.tool_call_id}",
            config=runtime.config,
        )

    return [send_parent_message]


def create_subagent_tools(sessions):
    def response(value: dict, runtime: ToolRuntime) -> Command:
        subagent_id = value.get("subagent_id")
        if subagent_id in sessions.records and value.get("status") in {
            "completed",
            "failed",
            "error",
        }:
            sessions.records[subagent_id]["collected"] = True
        return Command(
            update={
                "subagent_sessions": sessions.snapshot(),
                "messages": [
                    ToolMessage(
                        content=json.dumps(value, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id,
                        status="error" if value.get("status") in {"error", "failed"} else "success",
                        additional_kwargs={
                            "lambchat_subagent_id": subagent_id,
                            "lambchat_subagent_status": value.get("status"),
                        },
                    )
                ],
            }
        )

    @tool
    async def task(
        description: str, subagent_type: str, runtime: ToolRuntime, background: bool = False
    ) -> Command:
        """Delegate a NEW task to a role. background=true returns a stable subagent_id
        immediately so you can work and send instructions while it runs. Otherwise
        wait for completion. Use send_subagent_message to continue an existing ID,
        never task again for continuation. Wait for background results before synthesis."""
        sessions.restore(runtime.state.get("subagent_sessions", {}))
        try:
            value = await sessions.start(
                subagent_type,
                description,
                call_id=runtime.tool_call_id,
                config=runtime.config,
                background=background,
                initial_state={
                    "files": runtime.state.get("files", {}),
                    "messages": runtime.state.get("messages", []),
                },
            )
        except GraphBubbleUp:
            raise
        except Exception:
            value = {
                "status": "error",
                "error": "Unable to load this subagent; search its role again.",
            }
        return response(value, runtime)

    @tool
    async def send_subagent_message(
        subagent_id: str, message: str, runtime: ToolRuntime, background: bool = False
    ) -> Command:
        """Send instructions to an existing subagent in this conversation. While it
        runs, queue the message for its next model call; do not restart it. After it
        finishes, continue the SAME conversation, role and history. background=true
        returns immediately; otherwise wait for the resumed execution. A running
        recipient always returns immediately. Use wait_subagent to collect its result."""
        sessions.restore(runtime.state.get("subagent_sessions", {}))
        try:
            value = await sessions.send(
                subagent_id,
                message,
                config=runtime.config,
                background=background,
                message_id=f"subagent-message-{runtime.tool_call_id}",
            )
        except GraphBubbleUp:
            raise
        except Exception:
            value = {
                "subagent_id": subagent_id,
                "status": "error",
                "error": "Unable to continue this subagent; check role access and retry.",
            }
        return response(value, runtime)

    @tool
    async def wait_subagent(subagent_id: str, runtime: ToolRuntime) -> Command:
        """Wait for the existing subagent to finish, deliver queued messages, and
        return its result. A child message may return early with messages_pending=true;
        read it, reply if needed and wait again. Also surfaces pending human approval through the
        normal approval flow. Use before final synthesis of background work."""
        sessions.restore(runtime.state.get("subagent_sessions", {}))
        try:
            value = await sessions.wait(
                subagent_id, config=runtime.config, waiter_id=runtime.tool_call_id
            )
        except GraphBubbleUp:
            raise
        except Exception:
            value = {
                "subagent_id": subagent_id,
                "status": "error",
                "error": "Unable to load this subagent's result.",
            }
        return response(value, runtime)

    task.metadata = {"lambchat_managed_task": True}
    return [task, send_subagent_message, wait_subagent]
