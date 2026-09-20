"""Planning policy must give models concrete todo triggers and compliance."""

from src.agents.core.prompt_policy import PROGRESS_POLICY
from src.agents.core.todo_middleware import TODO_SYSTEM_PROMPT, TODO_TOOL_DESCRIPTION


def test_progress_policy_defers_todo_trigger_to_middleware() -> None:
    """write_todos 触发指引的唯一系统级注入点是 TodoListMiddleware 的
    system_prompt（主 agent 与全部子代理中间件栈都带它）；PROGRESS_POLICY
    不得复读同一触发条件——每个请求双份近逐字注入纯属 token 浪费，只保留
    阶段播报与真实性纪律。"""
    assert "write_todos" not in PROGRESS_POLICY
    assert "one-line phase updates" in PROGRESS_POLICY
    assert "never invent results" in PROGRESS_POLICY


def test_todo_trigger_phrases_live_in_middleware_system_prompt() -> None:
    # 阈值具体化：模型对"multi-step"主观跳过，需要可判定的触发条件；
    # 显式要求计划/清单/write_todos 时必须遵守（staging 实测会被模型忽略）。
    for phrase in (
        "3+ steps",
        "multiple tool calls",
        "before any tool call",
        "Explicit",
        "always call first",
    ):
        assert phrase in TODO_SYSTEM_PROMPT


def test_scheduled_task_guidance_has_single_prompt_source(monkeypatch) -> None:
    """scheduled_task 提示只允许一个来源（persona 行为引导首段）；
    MAIN_AGENT_PROMPT_SECTIONS 不得复读——开启开关时曾双份注入每个请求。
    reload 让模块级条件段在强制 True 下重新求值，本地 .env 关闭开关时
    也能钉住该行为。"""
    from importlib import reload

    from src.agents.core import persona, subagent_prompts

    monkeypatch.setattr(persona.settings, "ENABLE_SCHEDULED_TASK", True)
    sections = reload(subagent_prompts).MAIN_AGENT_PROMPT_SECTIONS

    assert "scheduled_task_create" in persona._build_behavior_guide()
    assert not any("scheduled_task_create" in section for section in sections)


def test_todo_tool_description_pins_actionable_threshold() -> None:
    assert "two or more tool calls" in TODO_TOOL_DESCRIPTION
    assert "always call it" in TODO_TOOL_DESCRIPTION


def test_todo_middleware_injects_system_level_planning_guidance() -> None:
    """Todo 触发指引随 TodoListMiddleware 的 system_prompt 注入：主 agent
    与子代理栈都挂该中间件，是 write_todos 指引的唯一系统级通道。"""
    from src.agents.core.todo_middleware import create_todo_middleware

    system_prompt = create_todo_middleware().system_prompt
    assert system_prompt.strip()
    assert "3+ steps" in system_prompt
    assert "always call first" in system_prompt
    assert "write_todos" in system_prompt


def test_write_todos_schema_inlines_refs_for_compatible_providers() -> None:
    """staging 实测：智谱 Anthropic 兼容端点不解析 $defs/$ref，write_todos 与
    task（均含 $ref schema）被静默丢弃，模型只能幻称调用；扁平 schema 工具
    （read_file/memory_retain 等）全部正常。序列化 schema 必须零 $ref/$defs。"""
    import json

    from langchain_core.utils.function_calling import convert_to_openai_tool

    from src.agents.core.todo_middleware import create_todo_middleware

    payload = json.dumps(convert_to_openai_tool(create_todo_middleware().tools[0]))
    assert '"write_todos"' in payload
    assert "$ref" not in payload
    assert "$defs" not in payload
    assert '"content"' in payload and '"status"' in payload


def test_flat_write_todos_updates_state_like_upstream() -> None:
    import asyncio
    from types import SimpleNamespace

    from src.agents.core.todo_middleware import create_todo_middleware

    tool = create_todo_middleware().tools[0]
    result = asyncio.new_event_loop().run_until_complete(
        tool.coroutine(
            todos=[{"content": "step", "status": "in_progress"}],
            runtime=SimpleNamespace(tool_call_id="t1"),
        )
    )
    assert result.update["todos"] == [{"content": "step", "status": "in_progress"}]
    assert result.update["messages"][0].tool_call_id == "t1"


def test_todo_system_prompt_breaks_overthinking_loops() -> None:
    """GAIA 失败归因（2026-09-20）：3/7 失败是模型纯思考 420-660s 不调任何
    工具直到超时（flash 与 glm-5.3 都会）。随中间件注入的指引必须含
    「想太久就立刻行动」的明确指令。"""
    from src.agents.core.todo_middleware import TODO_SYSTEM_PROMPT

    assert "Act over endless reasoning" in TODO_SYSTEM_PROMPT
    assert "call a tool now" in TODO_SYSTEM_PROMPT
