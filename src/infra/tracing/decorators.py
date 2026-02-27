"""Tracing decorators."""

import os
from typing import Any, Callable, TypeVar, cast

F = TypeVar("F", bound=Callable[..., Any])


def traced(name: str = "", run_type: str = "chain") -> Callable[[F], F]:
    """
    Decorator for tracing functions with LangSmith.

    Usage:
        @traced(name="my_function", run_type="tool")
        async def my_function(arg: str) -> str:
            return result

    Args:
        name: Name for the trace (default: function name)
        run_type: Type of run (chain, tool, llm, etc.)
    """

    def decorator(func: F) -> F:
        # If tracing is disabled, return original function
        if os.getenv("LANGSMITH_TRACING", "false").lower() != "true":
            return func

        # Import here to avoid circular imports
        from langsmith import traceable

        # Apply langsmith traceable decorator with keyword-only run_type
        decorated = traceable(name=name or func.__name__, run_type=run_type)  # type: ignore[call-overload]
        return cast(F, decorated(func))

    return decorator
