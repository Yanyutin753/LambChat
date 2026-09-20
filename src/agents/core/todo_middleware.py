"""Shared Todo middleware configuration for user-facing Agents."""

from langchain.agents.middleware import TodoListMiddleware

# Todo 触发指引的唯一系统级注入点：主 agent 与全部子代理的中间件栈都挂
# 本中间件（见 test_todo_middleware_registration）；PROGRESS_POLICY 不再
# 复读同一触发条件（曾双份近逐字注入每个请求）。
TODO_SYSTEM_PROMPT = (
    "### Todo Planning\n"
    "For multi-step work (3+ steps or multiple tool calls), call `write_todos` "
    "with the plan before any tool call and keep statuses current. Explicit "
    "plan/checklist/`write_todos` requests: always call first. Skip trivial "
    "one-step requests.\n"
    "Act over endless reasoning: prefer a tool call or exact computation over "
    "long mental reasoning; if you have reasoned at length without acting, "
    "call a tool now."
)

TODO_TOOL_DESCRIPTION = (
    "Create or replace the Todo plan for the current task.\n\n"
    "Use this for multi-step work: two or more tool calls, three or more distinct\n"
    "steps, uncertainty, external checks, or an explicit Todo/plan request. Skip\n"
    "trivial one-step requests. The tool replaces the entire list, so include\n"
    "every item that should remain. Start the first active item as `in_progress`,\n"
    "mark items `completed` immediately after verification, and remove stale\n"
    "items. Call it at most once per model turn; update the plan again when the\n"
    "phase changes. If the user explicitly asks for a plan or for this tool,\n"
    "always call it before doing the work.\n"
)


def create_todo_middleware() -> TodoListMiddleware:
    """Expose Todo state/tools with planning guidance that reaches every main agent."""
    return TodoListMiddleware(
        system_prompt=TODO_SYSTEM_PROMPT, tool_description=TODO_TOOL_DESCRIPTION
    )
