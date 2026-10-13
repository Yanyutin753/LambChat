"""PTC contract exercised through the installed QuickJS eval tool."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolRuntime

from src.infra.agent.middleware.code_interpreter import create_code_interpreter_middleware
from src.infra.tool.web_fetch_tool import web_fetch
from src.infra.tool.web_search_tool import web_search
from src.kernel.config import settings


class Audit(AsyncCallbackHandler):
    def __init__(self):
        self.ends = []
        self.errors = []

    async def on_tool_end(self, output, **kwargs):
        self.ends.append(output)

    async def on_tool_error(self, error, **kwargs):
        self.errors.append(error)


async def prepared(monkeypatch, tools=None):
    monkeypatch.setattr(settings, "ENABLE_CODE_INTERPRETER", True)
    monkeypatch.setattr(settings, "CODE_INTERPRETER_PTC_TOOLS", "web_search,web_fetch,execute")
    interpreter = create_code_interpreter_middleware({"enable_code_interpreter": True})[0]
    state = interpreter.before_agent({}, SimpleNamespace())
    request = SimpleNamespace(tools=tools or [web_search, web_fetch], state=state)
    interpreter._prepare_for_call(request)
    audit = Audit()
    runtime = ToolRuntime(
        state=state,
        tool_call_id="eval-parent",
        context=None,
        store=None,
        stream_writer=lambda value: None,
        tools=tools or [web_search, web_fetch],
        config={
            "callbacks": [audit],
            "configurable": {"user_id": "user-a", "session_id": "session-a"},
        },
    )
    return interpreter, runtime, audit


async def evaluate(interpreter, runtime, code):
    return await interpreter.tools[0].coroutine(runtime=runtime, code=code)


async def close(interpreter, runtime):
    await interpreter._registry.aevict(runtime.state["_quickjs_slot_id"])


async def test_real_quickjs_batches_native_results_and_preserves_sources(monkeypatch):
    async def fetch(url, limit):
        return {"success": True, "url": url, "content": "hello", "truncated": False}

    monkeypatch.setattr("src.infra.tool.web_fetch_tool.execute_web_fetch", fetch)
    interpreter, runtime, audit = await prepared(monkeypatch)
    try:
        message = await evaluate(
            interpreter,
            runtime,
            """(async () => {
          const rows = await Promise.all(["https://a.test", "https://b.test"].map(url => tools.webFetch({url})));
          return JSON.stringify(rows.filter(r => r.ok).map(r => ({text:r.data.content, source:r.sources[0]})));
        })()""",
        )
        assert '"text":"hello"' in message.content
        assert "https://a.test" in message.content
        assert "tool_call_id" in message.content
        assert audit.ends
        direct = await web_fetch.ainvoke({"url": "https://a.test"})
        assert json.loads(direct)["content"] == "hello"
        assert "sources" not in json.loads(direct)
    finally:
        await close(interpreter, runtime)


async def test_real_quickjs_bounds_data_without_breaking_structure(monkeypatch):
    async def fetch(url, limit):
        return {"success": True, "url": url, "content": "x" * 20000}

    monkeypatch.setattr("src.infra.tool.web_fetch_tool.execute_web_fetch", fetch)
    interpreter, runtime, _ = await prepared(monkeypatch)
    try:
        message = await evaluate(
            interpreter,
            runtime,
            """(async () => {
          const r = await tools.webFetch({url:"https://a.test"});
          return JSON.stringify({ok:r.ok,truncated:r.truncated,n:r.data.content.length,s:r.sources});
        })()""",
        )
        assert '"ok":true' in message.content
        assert '"truncated":true' in message.content
        assert "https://a.test" in message.content
        assert "20000" not in message.content
    finally:
        await close(interpreter, runtime)


async def test_real_quickjs_recovers_native_failure_and_keeps_error_audit(monkeypatch):
    async def fetch(url, limit):
        if "bad" in url:
            return {"success": False, "error": "web_fetch_failed: unavailable"}
        return {"success": True, "url": url, "content": "ok"}

    monkeypatch.setattr("src.infra.tool.web_fetch_tool.execute_web_fetch", fetch)
    interpreter, runtime, audit = await prepared(monkeypatch)
    try:
        message = await evaluate(
            interpreter,
            runtime,
            """(async () => {
          const rows = await Promise.all(["https://bad.test","https://ok.test"].map(url => tools.webFetch({url})));
          return JSON.stringify(rows.map(r => ({ok:r.ok,error:r.error})));
        })()""",
        )
        assert '"ok":false' in message.content
        assert '"code":"web_fetch_failed"' in message.content
        assert '"ok":true' in message.content
        assert any(isinstance(x, dict) and x.get("error") for x in audit.ends)
        original_errors = [x for x in audit.ends if getattr(x, "status", None) == "error"]
        assert original_errors
    finally:
        await close(interpreter, runtime)


async def test_real_quickjs_never_exposes_configured_write_or_spoofed_tools(monkeypatch):
    async def forbidden(url: str) -> str:
        raise AssertionError("must never execute")

    spoof = StructuredTool.from_function(
        coroutine=forbidden, name="web_fetch", description="Write data"
    )
    execute = StructuredTool.from_function(
        coroutine=forbidden, name="execute", description="Execute shell"
    )
    interpreter, runtime, _ = await prepared(monkeypatch, [spoof, execute])
    try:
        message = await evaluate(
            interpreter, runtime, "JSON.stringify([typeof tools.webFetch, typeof tools.execute])"
        )
        assert '["undefined","undefined"]' in message.content
    finally:
        await close(interpreter, runtime)


async def test_real_quickjs_cancellation_drains_hosts_and_limits_concurrency(monkeypatch):
    active = 0
    peak = 0
    started = asyncio.Event()

    async def fetch(url, limit):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    monkeypatch.setattr("src.infra.tool.web_fetch_tool.execute_web_fetch", fetch)
    interpreter, runtime, _ = await prepared(monkeypatch)
    try:
        task = asyncio.create_task(
            evaluate(
                interpreter,
                runtime,
                """Promise.all(Array.from({length:8},(_,i)=>tools.webFetch({url:"https://a.test/"+i})))""",
            )
        )
        await asyncio.wait_for(started.wait(), 5)
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert peak <= 3
        assert active == 0
    finally:
        await close(interpreter, runtime)


async def test_real_quickjs_rejects_33rd_host_call(monkeypatch):
    calls = 0

    async def fetch(url, limit):
        nonlocal calls
        calls += 1
        return {"success": True, "url": url, "content": "ok"}

    monkeypatch.setattr("src.infra.tool.web_fetch_tool.execute_web_fetch", fetch)
    interpreter, runtime, _ = await prepared(monkeypatch)
    try:
        message = await evaluate(
            interpreter,
            runtime,
            """(async () => {
          for(let i=0;i<33;i++) await tools.webFetch({url:"https://a.test/"+i});
          return "unexpected";
        })()""",
        )
        assert "PTCCallBudgetExceeded" in message.content
        assert calls == 32
    finally:
        await close(interpreter, runtime)


async def test_real_quickjs_keeps_malformed_json_as_text_and_passes_config(monkeypatch):
    received = []

    async def malformed(url: str, config: RunnableConfig, max_chars: int = 32768) -> str:
        received.append(config)
        return '{"content":broken'

    monkeypatch.setattr(web_fetch, "coroutine", malformed)
    interpreter, runtime, audit = await prepared(monkeypatch)
    try:
        message = await evaluate(
            interpreter,
            runtime,
            """(async () => {
          const r=await tools.webFetch({url:"https://a.test"});
          return JSON.stringify({ok:r.ok,type:typeof r.data,s:r.sources});
        })()""",
        )
        assert '"ok":true' in message.content
        assert '"type":"string"' in message.content
        assert received[0]["configurable"]["user_id"] == "user-a"
        assert received[0]["configurable"]["session_id"] == "session-a"
        original_ends = [x for x in audit.ends if getattr(x, "name", None) == "web_fetch"]
        assert original_ends
        assert original_ends[0].tool_call_id in message.content
    finally:
        await close(interpreter, runtime)


async def test_real_quickjs_partial_host_timeout_preserves_successful_peer(monkeypatch):
    from src.infra.agent.middleware import ptc_adapter

    active = 0
    monkeypatch.setattr(ptc_adapter, "HOST_TIMEOUT_SECONDS", 0.05)

    async def fetch(url, limit):
        nonlocal active
        active += 1
        try:
            if "slow" in url:
                await asyncio.Event().wait()
            return {"success": True, "url": url, "content": "ok"}
        finally:
            active -= 1

    monkeypatch.setattr("src.infra.tool.web_fetch_tool.execute_web_fetch", fetch)
    interpreter, runtime, audit = await prepared(monkeypatch)
    try:
        message = await evaluate(
            interpreter,
            runtime,
            """(async () => {
          const rows=await Promise.all(["https://slow.test","https://ok.test"].map(url=>tools.webFetch({url})));
          return JSON.stringify(rows.map(r=>({ok:r.ok,error:r.error})));
        })()""",
        )
        assert '"code":"ptc_host_timeout"' in message.content
        assert '"ok":true' in message.content
        assert active == 0
        assert audit.errors
    finally:
        await close(interpreter, runtime)


async def test_real_quickjs_overall_deadline_cancels_waiting_hosts(monkeypatch):
    from src.infra.agent.middleware import ptc_adapter

    monkeypatch.setattr(ptc_adapter, "PROGRAM_TIMEOUT_SECONDS", 0.05)
    active = 0

    async def fetch(url, limit):
        nonlocal active
        active += 1
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    monkeypatch.setattr("src.infra.tool.web_fetch_tool.execute_web_fetch", fetch)
    interpreter, runtime, _ = await prepared(monkeypatch)
    try:
        message = await evaluate(interpreter, runtime, 'tools.webFetch({url:"https://slow.test"})')
        assert message.status == "error"
        assert "Timeout" in message.content
        assert active == 0
    finally:
        await close(interpreter, runtime)


async def test_tool_node_injects_eval_runtime_and_preserves_original_tool(monkeypatch):
    from langchain_core.messages import AIMessage
    from langgraph.prebuilt import ToolNode
    from langgraph.runtime import Runtime

    async def fetch(url, limit):
        return {"success": True, "url": url, "content": "node-ok"}

    monkeypatch.setattr("src.infra.tool.web_fetch_tool.execute_web_fetch", fetch)
    interpreter, runtime, _ = await prepared(monkeypatch)
    try:
        node = ToolNode([interpreter.tools[0], web_fetch])
        state = {
            **runtime.state,
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "eval",
                            "args": {
                                "code": '(async()=>JSON.stringify((await tools.webFetch({url:"https://a.test"})).data))()'
                            },
                            "id": "eval-node",
                            "type": "tool_call",
                        }
                    ],
                )
            ],
        }
        output = await node.ainvoke(state, config=runtime.config, runtime=Runtime())
        message = output["messages"][0]
        assert message.status == "success"
        assert "node-ok" in message.content
        assert node.tools_by_name["web_fetch"] is web_fetch
    finally:
        await close(interpreter, runtime)
