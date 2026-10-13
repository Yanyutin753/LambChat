"""Stop graph recovery when a prior external tool result cannot be confirmed."""

from inspect import getclosurevars
from types import CodeType
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from src.kernel.errors import AppError, ErrorCode


def _nested_codes(code: CodeType) -> set[CodeType]:
    codes = {code}
    for value in code.co_consts:
        if isinstance(value, CodeType):
            codes.update(_nested_codes(value))
    return codes


def _readonly(tool: Any) -> bool:
    from src.infra.agent.middleware.ptc_adapter import (
        create_bounded_interpreter,
        is_read_only_candidate,
    )

    if tool is None:
        return False
    if is_read_only_candidate(tool):
        return True
    code = getattr(getattr(tool, "coroutine", None), "__code__", None)
    if tool.name == "eval":
        from langchain_quickjs import CodeInterpreterMiddleware

        coroutine = getattr(tool, "coroutine", None)
        if code is None or not callable(coroutine):
            return False
        bounded = code in _nested_codes(create_bounded_interpreter.__code__)
        original = (
            getclosurevars(coroutine).nonlocals.get("original_eval") if bounded else coroutine
        )
        if not callable(original):
            return False
        if getattr(original, "__code__", None) not in _nested_codes(
            CodeInterpreterMiddleware._build_tool.__code__
        ):
            return False
        owner = getclosurevars(original).nonlocals.get("middleware")
        return owner is not None and owner._subagents is False and (bounded or not owner._ptc)
    if tool.name in {"ls", "read_file", "glob", "grep"}:
        from deepagents.middleware.filesystem import FilesystemMiddleware

        factory = getattr(FilesystemMiddleware, f"_create_{tool.name}_tool")
        return code is not None and code in _nested_codes(factory.__code__)
    return False


def _results(value: Any) -> set[str]:
    answered: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, ToolMessage):
            answered.add(item.tool_call_id)
        elif isinstance(item, AIMessage):
            # A messages write may include history followed by a reused call ID.
            for call in item.tool_calls:
                identity = call.get("id")
                if isinstance(identity, str):
                    answered.discard(identity)
        elif isinstance(item, (list, tuple)):
            for message in item:
                visit(message)
        elif isinstance(item, dict) and set(item) == {"$writes"}:
            # LangGraph aggregates repeated writes to one channel this way.
            visit(item["$writes"])

    visit(value)
    return answered


def _uncertain(calls=()) -> AppError:
    return AppError(
        ErrorCode.TASK_RECOVERY_UNCERTAIN_EFFECT,
        args={"tool_calls": [{"id": call.get("id"), "name": call.get("name")} for call in calls]},
    )


async def guard_graph_recovery(graph: Any, config: Any) -> None:
    """Inspect the actual inner checkpoint before starting any model or tool work.

    Pending results count only when already durable. An unresolved interrupt is
    safe to answer; a persisted resume value means its tool may already have run.
    Tool names alone never establish read-only execution authority.
    """
    try:
        snapshot = await graph.aget_state(config)
        if not snapshot.next and not snapshot.tasks:
            return
        saved = await graph.checkpointer.aget_tuple(snapshot.config)
        if saved is None:
            raise _uncertain()
        writes = saved.pending_writes or ()
        messages = snapshot.values.get("messages", [])
        # IDs can be reused by a model in later rounds. Only a result after
        # the corresponding call resolves it; ambiguous duplicate calls stay blocked.
        pending: dict[str, list[dict[str, Any]]] = {}
        for message in messages:
            if not isinstance(message, BaseMessage):
                raise _uncertain()
            if isinstance(message, AIMessage):
                for call in message.tool_calls:
                    identity = call.get("id")
                    if not isinstance(identity, str) or not identity:
                        raise _uncertain([call])
                    pending.setdefault(identity, []).append(dict(call))
            elif isinstance(message, ToolMessage):
                identity = message.tool_call_id
                if len(pending.get(identity, [])) == 1:
                    del pending[identity]
        task_ids = {task.id for task in snapshot.tasks}
        message_outputs = [
            task.result.get("messages") for task in snapshot.tasks if isinstance(task.result, dict)
        ]
        message_outputs.extend(
            value
            for task_id, channel, value in writes
            if task_id in task_ids and channel == "messages"
        )
        answered = _results(message_outputs)
        for identity in answered:
            if len(pending.get(identity, [])) == 1:
                del pending[identity]
        if not pending:
            return

        resumed_tasks = {task_id for task_id, channel, _ in writes if channel == "__resume__"}
        resolved_interrupts = {
            key
            for _, channel, value in writes
            if channel == "__resume__" and isinstance(value, dict)
            for key in value
        }
        interrupt_ids = {item.id for task in snapshot.tasks for item in task.interrupts}
        legacy_global_resume = any(
            channel == "__resume__"
            and task_id not in task_ids
            and (not isinstance(value, dict) or not set(value).issubset(interrupt_ids))
            for task_id, channel, value in writes
        )
        fresh_approvals = set()
        for task in snapshot.tasks:
            if legacy_global_resume or task.id in resumed_tasks:
                continue
            for interrupt in task.interrupts:
                if interrupt.id in resolved_interrupts:
                    continue
                value = interrupt.value
                call_id = value.get("tool_call_id") if isinstance(value, dict) else None
                if call_id and len(pending.get(call_id, [])) == 1:
                    fresh_approvals.add(call_id)
                elif (
                    not call_id
                    and sum(map(len, pending.values())) == 1
                    and len(snapshot.tasks) == 1
                ):
                    # A single tool can call ask_human without forwarding its ID.
                    fresh_approvals.update(pending)

        tool_node = graph.builder.nodes.get("tools")
        tools = getattr(getattr(tool_node, "runnable", None), "tools_by_name", {})
        unsafe = [
            call
            for identity, calls in pending.items()
            for call in calls
            if identity not in fresh_approvals and not _readonly(tools.get(call.get("name")))
        ]
        if unsafe:
            raise _uncertain(unsafe)
    except AppError as error:
        if error.error_code is ErrorCode.TASK_RECOVERY_UNCERTAIN_EFFECT:
            raise
        raise _uncertain() from None
    except Exception:
        # Never turn unavailable/corrupt checkpoint authority into permission to replay.
        raise _uncertain() from None
