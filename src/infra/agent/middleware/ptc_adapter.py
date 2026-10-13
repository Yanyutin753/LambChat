"""Read-only QuickJS bridges with bounded native results and host lifetimes."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.callbacks.manager import AsyncCallbackManagerForToolRun
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolRuntime
from pydantic import ConfigDict

MAX_PTC_CALLS = 32
PROGRAM_TIMEOUT_SECONDS = 60
HOST_TIMEOUT_SECONDS = 20
MAX_RESULT_CHARS = 8000
MAX_CONCURRENT_HOSTS = 3
READ_ONLY_NAMES = frozenset({"web_search", "web_fetch"})


@dataclass
class PTCProgram:
    deadline: float = field(default_factory=lambda: time.monotonic() + PROGRAM_TIMEOUT_SECONDS)
    semaphore: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(MAX_CONCURRENT_HOSTS)
    )
    tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    closed: bool = False

    async def close(self) -> None:
        self.closed = True
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


ACTIVE_PROGRAM: ContextVar[PTCProgram | None] = ContextVar("quickjs_ptc_program", default=None)


def is_read_only_candidate(tool: BaseTool) -> bool:
    """A configurable name is insufficient: retain the built-in implementation/schema."""
    if tool.name not in READ_ONLY_NAMES:
        return False
    from src.infra.tool.web_fetch_tool import web_fetch
    from src.infra.tool.web_search_tool import web_search

    original = {"web_fetch": web_fetch, "web_search": web_search}[tool.name]
    original_coroutine = getattr(original, "coroutine", None)
    return (
        callable(original_coroutine)
        and getattr(tool, "coroutine", None) is original_coroutine
        and tool.args_schema is original.args_schema
    )


def _sources(data: Any, args: dict[str, Any], tool_name: str, call_id: str) -> list[dict[str, str]]:
    urls: dict[str, None] = {}
    if isinstance(args.get("url"), str):
        urls[args["url"]] = None
    if isinstance(data, dict):
        if isinstance(data.get("url"), str):
            urls[data["url"]] = None
        for row in data.get("results", []) if isinstance(data.get("results"), list) else []:
            if isinstance(row, dict) and isinstance(row.get("url"), str):
                urls[row["url"]] = None
    base = {"tool_name": tool_name, "tool_call_id": call_id}
    return [{**base, "url": url} for url in list(urls)[:32]] or [base]


def _bounded_data(data: Any) -> tuple[Any, bool]:
    serialized = json.dumps(data, ensure_ascii=False, default=str)
    if len(serialized) <= MAX_RESULT_CHARS:
        return data, False
    # Keep ordinary fetch/search fields navigable; oversized containers fall back
    # to a bounded text value, never an invalid JSON fragment to parse in JS.
    budget = MAX_RESULT_CHARS - 1000

    def clip(value: Any, depth: int = 0) -> Any:
        nonlocal budget
        if depth > 20 or budget <= 0:
            return None
        if isinstance(value, str):
            clipped_text = value[:budget]
            budget -= len(clipped_text)
            return clipped_text
        if isinstance(value, dict):
            clipped_mapping: dict[str, Any] = {}
            for key, item in value.items():
                budget -= len(str(key)) + 8
                if budget <= 0:
                    break
                clipped_mapping[str(key)] = clip(item, depth + 1)
            return clipped_mapping
        if isinstance(value, list):
            clipped_sequence: list[Any] = []
            for item in value:
                budget -= 8
                if budget <= 0:
                    break
                clipped_sequence.append(clip(item, depth + 1))
            return clipped_sequence
        budget -= len(str(value)) + 8
        return value

    bounded = clip(data)
    if len(json.dumps(bounded, ensure_ascii=False, default=str)) > MAX_RESULT_CHARS:
        bounded = serialized[: MAX_RESULT_CHARS // 2]
    return bounded, True


def structured_result(
    raw: Any, *, args: dict[str, Any], tool_name: str, call_id: str
) -> dict[str, Any]:
    status_error = isinstance(raw, ToolMessage) and raw.status == "error"
    data = raw.content if isinstance(raw, ToolMessage) else raw
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            pass
    sources = _sources(data, args, tool_name, call_id)
    failure = status_error or (
        isinstance(data, dict)
        and (data.get("success") is False or data.get("ok") is False or bool(data.get("error")))
    )
    error = None
    if failure:
        native_error = data.get("error") if isinstance(data, dict) else data
        if isinstance(native_error, dict):
            code = str(native_error.get("code") or "ptc_tool_error")
            message = str(native_error.get("message") or "Tool execution failed")
        else:
            message = str(native_error or "Tool execution failed")
            prefix = message.split(":", 1)[0]
            code = prefix if re.fullmatch(r"[a-z][a-z0-9_]+", prefix) else "ptc_tool_error"
        error = {"code": code, "message": message[:500]}
    bounded, truncated = _bounded_data(data)
    return {
        "ok": not failure,
        "data": bounded,
        "sources": sources,
        "truncated": truncated or (isinstance(data, dict) and data.get("truncated") is True),
        "error": error,
    }


class _NativeFailureStatus(BaseCallbackHandler):
    # Normalize the original invocation before inherited tracing callbacks run.
    run_inline = True

    def __init__(self) -> None:
        self.run_id: Any = None
        self.parent_run_id: Any = None
        self.ended = False

    def on_tool_start(self, serialized: Any, input_str: str, **kwargs: Any) -> None:
        self.run_id = kwargs["run_id"]
        self.parent_run_id = kwargs.get("parent_run_id")

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        self.ended = True

    async def finish_cancelled(self, callbacks: Any, error: BaseException, call_id: str) -> None:
        if self.run_id is None or self.ended:
            return
        self.ended = True
        manager = AsyncCallbackManagerForToolRun(
            run_id=self.run_id,
            parent_run_id=self.parent_run_id,
            handlers=callbacks.handlers,
            inheritable_handlers=callbacks.inheritable_handlers,
            tags=callbacks.tags,
            metadata=callbacks.metadata,
        )
        await manager.on_tool_error(error, tool_call_id=call_id)

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        self.ended = True
        if not isinstance(output, ToolMessage) or not isinstance(output.content, str):
            return
        try:
            data = json.loads(output.content)
        except ValueError:
            return
        if isinstance(data, dict) and (
            data.get("success") is False or data.get("ok") is False or data.get("error")
        ):
            output.status = "error"


class ReadOnlyPTCAdapter(BaseTool):
    """Call the authorized original tool through its real lifecycle and config."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    original: BaseTool

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("PTC adapters require the asynchronous interpreter")

    async def _arun(
        self, *args: Any, config: RunnableConfig, run_manager: Any = None, **kwargs: Any
    ) -> Any:
        program = ACTIVE_PROGRAM.get()
        call_id = f"ptc-{self.name}-{uuid.uuid4().hex}"
        if program is None or program.closed:
            raise RuntimeError("PTC host call outside active program")
        task = asyncio.current_task()
        assert task is not None
        program.tasks.add(task)
        tool_args = dict(kwargs)
        # A scalar schema can yield positional args; built-in web tools use object schemas.
        if args:
            raise ValueError("PTC web tools require named arguments")
        original_config: RunnableConfig = config.copy()
        normalizer = _NativeFailureStatus()
        callbacks = None
        if run_manager is not None:
            callbacks = run_manager.get_child()
            callbacks.handlers.insert(0, normalizer)
            original_config["callbacks"] = callbacks
        try:
            timeout = max(0, min(HOST_TIMEOUT_SECONDS, program.deadline - time.monotonic()))
            try:
                async with asyncio.timeout(timeout), program.semaphore:
                    raw = await self.original.ainvoke(
                        {"name": self.name, "args": tool_args, "id": call_id, "type": "tool_call"},
                        config=original_config,
                    )
            except TimeoutError:
                if callbacks is not None:
                    await normalizer.finish_cancelled(
                        callbacks,
                        TimeoutError("ptc_host_timeout: Read-only tool timed out"),
                        call_id,
                    )
                raw = {
                    "success": False,
                    "error": {"code": "ptc_host_timeout", "message": "Read-only tool timed out"},
                }
            except asyncio.CancelledError as exc:
                if callbacks is not None:
                    await normalizer.finish_cancelled(callbacks, exc, call_id)
                if run_manager is not None:
                    await run_manager.on_tool_error(exc)
                raise
            except Exception as exc:
                raw = {
                    "success": False,
                    "error": {
                        "code": "ptc_tool_error",
                        "message": str(exc) or "Tool execution failed",
                    },
                }
            return structured_result(raw, args=tool_args, tool_name=self.name, call_id=call_id)
        finally:
            program.tasks.discard(task)


def make_adapter(tool: BaseTool) -> ReadOnlyPTCAdapter:
    return ReadOnlyPTCAdapter(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        original=tool,
    )


def create_bounded_interpreter(**kwargs: Any) -> Any:
    """Use upstream explicit BaseTool registration without changing shared configuration."""
    import copy

    from langchain_quickjs import CodeInterpreterMiddleware

    class StructuredCodeInterpreterMiddleware(CodeInterpreterMiddleware):
        _borrowed_registry: bool = False

        def __del__(self) -> None:
            # Upstream owns/closes the registry in __del__; a request-local view
            # borrows it and must not tear down the real interpreter's context.
            if not getattr(self, "_borrowed_registry", False):
                getattr(super(), "__del__", lambda: None)()

        def _prepare_for_call(self, request: Any) -> str:
            local = copy.copy(self)
            local._borrowed_registry = True
            local._ptc = [
                make_adapter(tool)
                for tool in request.tools
                if isinstance(tool, BaseTool)
                and tool.name in (self._ptc or [])
                and is_read_only_candidate(tool)
            ]
            # Registry and per-slot bindings are shared; registration itself uses
            # the public explicit BaseTool PTC option on a request-local view.
            return CodeInterpreterMiddleware._prepare_for_call(local, request)

        def _build_tool(self) -> BaseTool:
            tool = super()._build_tool()
            original_eval = getattr(tool, "coroutine", None)
            assert callable(original_eval)

            async def bounded_eval(runtime: ToolRuntime[None, Any], code: str) -> ToolMessage:
                program = PTCProgram()
                token = ACTIVE_PROGRAM.set(program)
                try:
                    try:
                        async with asyncio.timeout(PROGRAM_TIMEOUT_SECONDS):
                            return await original_eval(runtime=runtime, code=code)
                    except TimeoutError:
                        return ToolMessage(
                            content="Error [Timeout]: Program exceeded its execution deadline",
                            name=tool.name,
                            tool_call_id=runtime.tool_call_id,
                            status="error",
                        )
                finally:
                    await program.close()
                    ACTIVE_PROGRAM.reset(token)

            def bounded_sync_eval(runtime: ToolRuntime[None, Any], code: str) -> ToolMessage:
                return asyncio.run(bounded_eval(runtime, code))

            return tool.model_copy(update={"coroutine": bounded_eval, "func": bounded_sync_eval})

    return StructuredCodeInterpreterMiddleware(**kwargs)
