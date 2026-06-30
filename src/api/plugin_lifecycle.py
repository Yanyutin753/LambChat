"""Shared Plugin Runtime lifecycle hook execution helpers."""

from __future__ import annotations

import inspect
from importlib import import_module

from src.kernel.extensions import PluginHookExecutionResult, PluginRuntime
from src.kernel.extensions.registry import LifecyclePhase, PluginLifecycleHookRegistration

PLUGIN_LIFECYCLE_HOOK_TIMEOUT_SECONDS = 5.0


def resolve_plugin_lifecycle_hook(registration: PluginLifecycleHookRegistration):
    module_name, separator, callable_name = registration.module.partition(":")
    if not separator or not callable_name:
        raise ValueError(
            f"plugin lifecycle hook must use module:callable syntax: {registration.module}"
        )
    module = import_module(module_name)
    hook_callable = getattr(module, callable_name)
    if not callable(hook_callable):
        raise TypeError(f"plugin lifecycle hook is not callable: {registration.module}")
    return hook_callable


async def invoke_plugin_lifecycle_hook(
    registration: PluginLifecycleHookRegistration,
) -> None:
    hook_callable = resolve_plugin_lifecycle_hook(registration)
    signature = inspect.signature(hook_callable)
    required_positionals = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }
    ]
    if required_positionals:
        result = hook_callable(registration)
    else:
        result = hook_callable()
    if inspect.isawaitable(result):
        await result


async def run_plugin_lifecycle_hooks(
    runtime: PluginRuntime,
    *,
    phase: LifecyclePhase,
    plugin_id: str | None = None,
    timeout_seconds: float = PLUGIN_LIFECYCLE_HOOK_TIMEOUT_SECONDS,
) -> list[PluginHookExecutionResult]:
    return await runtime.execute_lifecycle_hooks(
        phase=phase,
        plugin_id=plugin_id,
        executor=invoke_plugin_lifecycle_hook,
        timeout_seconds=timeout_seconds,
    )
