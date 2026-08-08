"""Shared compact todo middleware configuration."""

from langchain.agents.middleware import TodoListMiddleware


def create_todo_middleware() -> TodoListMiddleware:
    """Expose todo state and tools without LangChain's duplicate prompt guide."""
    return TodoListMiddleware(system_prompt="")
