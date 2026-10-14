"""Conversation controls for TeamAgent's persistent subagents."""

import json
from typing import Annotated

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.types import Command
from pydantic import Field


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
        evidence = sessions.records.get(subagent_id, {}).get("evidence", [])
        if subagent_id in sessions.records and value.get("status") in {
            "completed",
            "failed",
            "error",
            "cancelled",
            "timed_out",
        }:
            sessions.records[subagent_id]["collected"] = True
        return Command(
            update={
                "subagent_sessions": sessions.snapshot(),
                "messages": [
                    ToolMessage(
                        content=json.dumps(value, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id,
                        status="error"
                        if value.get("status") in {"error", "failed", "timed_out"}
                        else "success",
                        additional_kwargs={
                            "lambchat_subagent_id": subagent_id,
                            "lambchat_subagent_status": value.get("status"),
                            "lambchat_subagent_partial_result": value.get("partial_result") is True,
                            "lambchat_subagent_unchanged": value.get("unchanged") is True,
                            "lambchat_subagent_evidence": evidence
                            if (value.get("status") == "completed" or value.get("partial_result"))
                            and not value.get("result_collected")
                            else [],
                            "lambchat_evidence_scope_version": evidence[-1].get("scope_version", "")
                            if evidence
                            else "",
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
    async def wait_subagent(
        subagent_id: str,
        runtime: ToolRuntime,
        timeout_seconds: Annotated[int, Field(ge=10, le=300)] = 120,
    ) -> Command:
        """Use an event-driven bounded wait for the child, normally 120 seconds (10–300).
        Completion or parent mail wakes it immediately. wait_timed_out=true means the wait
        expired, not the child. Prefer longer waits to repeated status polling; do other
        independent work when appropriate. Collected final reports are not repeated.
        terminal=true means stop waiting. Missing IDs require list_subagents, not retries.
        Read messages_pending before waiting again; pending human approval uses the normal flow."""
        sessions.restore(runtime.state.get("subagent_sessions", {}))
        try:
            value = await sessions.wait(
                subagent_id,
                config=runtime.config,
                waiter_id=runtime.tool_call_id,
                timeout_seconds=timeout_seconds,
            )
        except GraphBubbleUp:
            raise
        except Exception:
            value = {
                "subagent_id": subagent_id,
                "status": "error",
                "error": "Unable to load this subagent's result.",
                "terminal": True,
                "reason": "status_unavailable",
                "guidance": "Do not repeatedly wait. Use list_subagents and check role access before continuing.",
            }
        return response(value, runtime)

    @tool
    async def cancel_subagent(subagent_id: str, runtime: ToolRuntime) -> Command:
        """Cancel one queued or running subagent in this conversation. Repeated cancellation
        is safe; other subagents keep running. Completed results remain available."""
        sessions.restore(runtime.state.get("subagent_sessions", {}))
        return response(await sessions.cancel(subagent_id), runtime)

    @tool
    async def list_subagents(runtime: ToolRuntime) -> Command:
        """List this conversation's subagents and their queued, running, approval or final states.
        This read-only operation does not start, cancel or wait for execution."""
        sessions.restore(runtime.state.get("subagent_sessions", {}))
        return response(sessions.list_subagents(), runtime)

    task.metadata = {"lambchat_managed_task": True}
    return [task, send_subagent_message, wait_subagent, cancel_subagent, list_subagents]
