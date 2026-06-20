"""Minimal controlled runtime model for build-time plugin manifests."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from time import perf_counter
from typing import Any, Literal

from src.kernel.extensions.manifest import PluginManifest
from src.kernel.extensions.registry import (
    LifecyclePhase,
    PluginAgentRegistration,
    PluginLifecycleHookRegistration,
    PluginRegistry,
    PluginRouteRegistration,
    PluginToolRegistration,
)
from src.kernel.extensions.resources import (
    PluginResourceCleanupStrategy,
    PluginResourceConflictError,
    PluginResourceLedger,
    PluginResourceRecord,
    PluginResourceRetentionPolicy,
    PluginResourceScope,
    PluginResourceType,
)


class PluginRuntimeStatus(str, Enum):
    """Runtime status maintained by the plugin runtime layer."""

    NOT_INSTALLED = "not_installed"
    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"
    UNINSTALLING = "uninstalling"
    UNINSTALLED = "uninstalled"


class PluginUnavailableError(RuntimeError):
    """Raised by route/tool guards when a plugin is not executable."""

    def __init__(self, message: str, *, plugin_id: str | None = None) -> None:
        super().__init__(message)
        self.plugin_id = plugin_id


class PluginRuntimeStateTransitionError(RuntimeError):
    """Raised when a requested runtime state change is not allowed."""


class PluginRuntimeUninstallError(RuntimeError):
    """Raised when uninstall execution is rejected by runtime safeguards."""


@dataclass(frozen=True)
class PluginRuntimeIssue:
    """Structured plugin-level validation or lifecycle error."""

    plugin_id: str
    code: str
    message: str
    phase: str = "validation"


@dataclass
class PluginRuntimeState:
    """Runtime state for one plugin manifest."""

    plugin_id: str
    status: PluginRuntimeStatus
    manifest: PluginManifest | None = None
    issues: list[PluginRuntimeIssue] = field(default_factory=list)
    state_source: str = "manifest_default"
    state_updated_at: datetime | None = None
    state_updated_by: str | None = None

    @property
    def enabled(self) -> bool:
        return self.status is PluginRuntimeStatus.ENABLED

    @property
    def executable(self) -> bool:
        return self.status is PluginRuntimeStatus.ENABLED and self.manifest is not None


HookExecutionStatus = Literal["succeeded", "failed", "timeout"]
HookExecutor = Callable[[PluginLifecycleHookRegistration], Any | Awaitable[Any]]


@dataclass(frozen=True)
class PluginHookExecutionResult:
    """Audit-friendly result for one lifecycle hook execution attempt."""

    plugin_id: str
    hook_name: str
    phase: LifecyclePhase
    status: HookExecutionStatus
    elapsed_ms: float
    error: str | None = None


class PluginRuntime:
    """Validate manifests, track state, and run controlled lifecycle hooks.

    This phase is intentionally static: no hot install or remote package loading.
    Uninstall only closes managed runtime state after dry-run safeguards. Invalid plugins move to ``error`` while the
    runtime remains usable for valid core and plugin declarations.
    """

    def __init__(
        self,
        manifests: Iterable[PluginManifest] | None = None,
        *,
        supported_api_versions: Iterable[str] = ("v1",),
        core_dependencies: Iterable[str] = (),
        resource_ledger: PluginResourceLedger | None = None,
    ) -> None:
        self._supported_api_versions = set(supported_api_versions)
        self._core_dependencies = set(core_dependencies)
        self.resource_ledger = resource_ledger or PluginResourceLedger()
        self._states: dict[str, PluginRuntimeState] = {}
        if manifests:
            self.load(manifests)

    def load(self, manifests: Iterable[PluginManifest]) -> None:
        """Load a static manifest list and convert errors into plugin states."""
        manifest_by_id: dict[str, PluginManifest] = {}
        duplicate_ids: set[str] = set()
        for manifest in manifests:
            if manifest.id in manifest_by_id:
                duplicate_ids.add(manifest.id)
                continue
            manifest_by_id[manifest.id] = manifest

        available_dependencies = set(manifest_by_id) | self._core_dependencies
        states: dict[str, PluginRuntimeState] = {}
        for plugin_id, manifest in manifest_by_id.items():
            issues = self._validate_manifest(
                manifest,
                available_dependencies=available_dependencies,
            )
            try:
                self._register_manifest_resources(manifest)
            except PluginResourceConflictError as exc:
                issues.append(
                    PluginRuntimeIssue(
                        plugin_id=plugin_id,
                        code="resource_conflict",
                        message=str(exc),
                    )
                )
            if plugin_id in duplicate_ids:
                issues.append(
                    PluginRuntimeIssue(
                        plugin_id=plugin_id,
                        code="duplicate_plugin_id",
                        message=f"plugin id is duplicated: {plugin_id}",
                    )
                )
            if issues:
                status = PluginRuntimeStatus.ERROR
            elif manifest.enabled_by_default:
                status = PluginRuntimeStatus.ENABLED
            else:
                status = PluginRuntimeStatus.DISABLED
            states[plugin_id] = PluginRuntimeState(
                plugin_id=plugin_id,
                status=status,
                manifest=manifest,
                issues=issues,
            )
        self._states = states

    def states(self) -> list[PluginRuntimeState]:
        return list(self._states.values())

    def get_state(self, plugin_id: str) -> PluginRuntimeState | None:
        return self._states.get(plugin_id)

    def is_enabled(self, plugin_id: str) -> bool:
        state = self.get_state(plugin_id)
        return bool(state and state.executable)

    def ensure_enabled(self, plugin_id: str) -> None:
        """Guard route/tool execution for a plugin contribution."""
        state = self.get_state(plugin_id)
        if state is None:
            raise PluginUnavailableError(
                f"plugin is not installed: {plugin_id}",
                plugin_id=plugin_id,
            )
        if not state.executable:
            raise PluginUnavailableError(
                f"plugin is not enabled: {plugin_id} ({state.status.value})",
                plugin_id=plugin_id,
            )

    def ensure_tool_available(self, tool_name: str) -> PluginToolRegistration:
        """Guard execution of a plugin-contributed tool by declared tool name."""
        for registration in self.tools(enabled_only=False):
            if registration.name == tool_name or tool_name in registration.legacy_ids:
                self.ensure_enabled(registration.plugin_id)
                return registration
        raise PluginUnavailableError(f"plugin tool is not registered: {tool_name}")

    def ensure_scheduler_job_available(self, job_id: str) -> PluginResourceRecord:
        """Guard scheduler dispatch for a plugin-owned scheduler job."""
        return self._ensure_resource_available(
            resource_type=PluginResourceType.SCHEDULER_JOB,
            resource_id=job_id,
            label="scheduler job",
        )

    def ensure_listener_available(self, listener_id: str) -> PluginResourceRecord:
        """Guard listener startup/dispatch for a plugin-owned listener."""
        return self._ensure_resource_available(
            resource_type=PluginResourceType.LISTENER,
            resource_id=listener_id,
            label="listener",
        )

    def ensure_channel_connector_available(self, connector_id: str) -> PluginResourceRecord:
        """Guard channel connector usage for a plugin-owned channel integration."""
        return self._ensure_resource_available(
            resource_type=PluginResourceType.CHANNEL_CONNECTOR,
            resource_id=connector_id,
            label="channel connector",
        )

    def enable_plugin(
        self,
        plugin_id: str,
        *,
        state_source: str = "runtime_control",
        updated_at: datetime | None = None,
        updated_by: str | None = None,
    ) -> PluginRuntimeState:
        """Enable a loaded plugin without installing packages or changing resources."""
        state = self.get_state(plugin_id)
        if state is None:
            raise PluginRuntimeStateTransitionError(f"plugin is not installed: {plugin_id}")
        if state.manifest is None:
            raise PluginRuntimeStateTransitionError(f"plugin manifest is unavailable: {plugin_id}")
        if state.status is PluginRuntimeStatus.ERROR:
            raise PluginRuntimeStateTransitionError(
                f"plugin is in error state and cannot be enabled: {plugin_id}"
            )
        if state.status in {
            PluginRuntimeStatus.UNINSTALLING,
            PluginRuntimeStatus.UNINSTALLED,
            PluginRuntimeStatus.NOT_INSTALLED,
        }:
            raise PluginRuntimeStateTransitionError(
                f"plugin cannot be enabled from {state.status.value}: {plugin_id}"
            )
        self._set_controlled_status(
            state,
            PluginRuntimeStatus.ENABLED,
            state_source=state_source,
            updated_at=updated_at,
            updated_by=updated_by,
        )
        return state

    def disable_plugin(
        self,
        plugin_id: str,
        *,
        state_source: str = "runtime_control",
        updated_at: datetime | None = None,
        updated_by: str | None = None,
    ) -> PluginRuntimeState:
        """Disable a loaded plugin without uninstalling packages or deleting resources."""
        state = self.get_state(plugin_id)
        if state is None:
            raise PluginRuntimeStateTransitionError(f"plugin is not installed: {plugin_id}")
        if state.status is PluginRuntimeStatus.ERROR:
            raise PluginRuntimeStateTransitionError(
                f"plugin is in error state and cannot be disabled: {plugin_id}"
            )
        if state.status in {
            PluginRuntimeStatus.UNINSTALLING,
            PluginRuntimeStatus.UNINSTALLED,
            PluginRuntimeStatus.NOT_INSTALLED,
        }:
            raise PluginRuntimeStateTransitionError(
                f"plugin cannot be disabled from {state.status.value}: {plugin_id}"
            )
        self._set_controlled_status(
            state,
            PluginRuntimeStatus.DISABLED,
            state_source=state_source,
            updated_at=updated_at,
            updated_by=updated_by,
        )
        return state

    def uninstall_plugin(
        self,
        plugin_id: str,
        *,
        state_source: str = "runtime_uninstall",
        updated_at: datetime | None = None,
        updated_by: str | None = None,
    ) -> PluginRuntimeState:
        """Mark an uninstallable plugin as uninstalled after external safeguards pass.

        This runtime phase does not execute arbitrary code removal or database/file
        deletion. It closes the executable surface by state and leaves resource
        cleanup to audited, plugin-owned strategies guarded by dry-run validation.
        """
        state = self.get_state(plugin_id)
        if state is None:
            raise PluginRuntimeUninstallError(f"plugin is not installed: {plugin_id}")
        manifest = state.manifest
        if manifest is None:
            raise PluginRuntimeUninstallError(f"plugin manifest is unavailable: {plugin_id}")
        if not manifest.uninstallable:
            raise PluginRuntimeUninstallError(
                f"plugin is protected and can only be disabled: {plugin_id}"
            )
        if state.status is PluginRuntimeStatus.ERROR:
            raise PluginRuntimeUninstallError(
                f"plugin is in error state and cannot be uninstalled: {plugin_id}"
            )
        if state.status is PluginRuntimeStatus.UNINSTALLED:
            return state
        if state.status is PluginRuntimeStatus.UNINSTALLING:
            raise PluginRuntimeUninstallError(f"plugin is already uninstalling: {plugin_id}")
        self._set_controlled_status(
            state,
            PluginRuntimeStatus.UNINSTALLED,
            state_source=state_source,
            updated_at=updated_at,
            updated_by=updated_by,
        )
        return state

    def apply_stored_status(
        self,
        plugin_id: str,
        status: PluginRuntimeStatus | str,
        *,
        updated_at: datetime | None = None,
        updated_by: str | None = None,
    ) -> PluginRuntimeState:
        """Apply a persisted enabled/disabled override after manifest validation."""
        resolved_status = PluginRuntimeStatus(status)
        if resolved_status is PluginRuntimeStatus.ENABLED:
            return self.enable_plugin(
                plugin_id,
                state_source="stored_override",
                updated_at=updated_at,
                updated_by=updated_by,
            )
        if resolved_status is PluginRuntimeStatus.DISABLED:
            return self.disable_plugin(
                plugin_id,
                state_source="stored_override",
                updated_at=updated_at,
                updated_by=updated_by,
            )
        if resolved_status is PluginRuntimeStatus.UNINSTALLED:
            return self.uninstall_plugin(
                plugin_id,
                state_source="stored_override",
                updated_at=updated_at,
                updated_by=updated_by,
            )
        raise PluginRuntimeStateTransitionError(
            f"stored status is not controllable: {plugin_id} ({resolved_status.value})"
        )

    def _set_controlled_status(
        self,
        state: PluginRuntimeState,
        status: PluginRuntimeStatus,
        *,
        state_source: str,
        updated_at: datetime | None,
        updated_by: str | None,
    ) -> None:
        state.status = status
        state.state_source = state_source
        state.state_updated_at = updated_at
        state.state_updated_by = updated_by

    def manifests(self, *, enabled_only: bool = True) -> list[PluginManifest]:
        states = self._states.values()
        if enabled_only:
            return [state.manifest for state in states if state.executable and state.manifest]
        return [state.manifest for state in states if state.manifest]

    def permissions(self, *, enabled_only: bool = True) -> list[str]:
        return PluginRegistry(self.manifests(enabled_only=enabled_only)).permissions(
            enabled_only=enabled_only
        )

    def routes(self, *, enabled_only: bool = True) -> list[PluginRouteRegistration]:
        return PluginRegistry(self.manifests(enabled_only=enabled_only)).routes(
            enabled_only=enabled_only
        )

    def tools(self, *, enabled_only: bool = True) -> list[PluginToolRegistration]:
        return PluginRegistry(self.manifests(enabled_only=enabled_only)).tools(
            enabled_only=enabled_only
        )

    def agents(self, *, enabled_only: bool = True) -> list[PluginAgentRegistration]:
        return PluginRegistry(self.manifests(enabled_only=enabled_only)).agents(
            enabled_only=enabled_only
        )

    def plugin_for_agent(self, agent_id: str) -> str | None:
        """Return the plugin that owns an agent catalog entry, if any."""
        for registration in self.agents(enabled_only=False):
            if registration.id == agent_id:
                return registration.plugin_id
        return None

    def ensure_agent_available(self, agent_id: str) -> PluginAgentRegistration | None:
        """Guard execution or catalog exposure for a plugin-owned agent."""
        for registration in self.agents(enabled_only=False):
            if registration.id == agent_id:
                self.ensure_enabled(registration.plugin_id)
                return registration
        return None

    def scheduler_jobs(self, *, enabled_only: bool = True) -> list[str]:
        return [
            job_id
            for manifest in self.manifests(enabled_only=enabled_only)
            for job_id in manifest.scheduler_jobs
        ]

    def listeners(self, *, enabled_only: bool = True) -> list[PluginResourceRecord]:
        return self._resource_records(
            resource_type=PluginResourceType.LISTENER,
            enabled_only=enabled_only,
        )

    def channel_connectors(self, *, enabled_only: bool = True) -> list[PluginResourceRecord]:
        return self._resource_records(
            resource_type=PluginResourceType.CHANNEL_CONNECTOR,
            enabled_only=enabled_only,
        )

    def _resource_records(
        self,
        *,
        resource_type: PluginResourceType,
        enabled_only: bool,
    ) -> list[PluginResourceRecord]:
        records = self.resource_ledger.list(resource_type=resource_type)
        if not enabled_only:
            return records
        return [
            record
            for record in records
            if (state := self.get_state(record.plugin_id)) is not None and state.executable
        ]

    def _ensure_resource_available(
        self,
        *,
        resource_type: PluginResourceType,
        resource_id: str,
        label: str,
    ) -> PluginResourceRecord:
        for record in self.resource_ledger.list(resource_type=resource_type):
            if record.resource_id == resource_id:
                self.ensure_enabled(record.plugin_id)
                return record
        raise PluginUnavailableError(f"plugin {label} is not registered: {resource_id}")

    def lifecycle_hooks(
        self,
        *,
        phase: LifecyclePhase | None = None,
        enabled_only: bool = True,
    ) -> list[PluginLifecycleHookRegistration]:
        return PluginRegistry(self.manifests(enabled_only=enabled_only)).lifecycle_hooks(
            phase=phase,
            enabled_only=enabled_only,
        )

    async def execute_lifecycle_hooks(
        self,
        *,
        phase: LifecyclePhase,
        executor: HookExecutor,
        timeout_seconds: float = 5.0,
    ) -> list[PluginHookExecutionResult]:
        """Execute lifecycle hooks with timeout/error isolation.

        Hook failures are recorded on the owning plugin and do not raise to the
        caller, preserving core startup/shutdown flow.
        """
        results: list[PluginHookExecutionResult] = []
        for registration in self.lifecycle_hooks(phase=phase):
            started = perf_counter()
            try:
                await asyncio.wait_for(
                    self._call_hook_executor(executor, registration),
                    timeout=timeout_seconds,
                )
                results.append(
                    PluginHookExecutionResult(
                        plugin_id=registration.plugin_id,
                        hook_name=registration.name,
                        phase=registration.phase,
                        status="succeeded",
                        elapsed_ms=(perf_counter() - started) * 1000,
                    )
                )
            except TimeoutError:
                error = f"hook timed out after {timeout_seconds:.3f}s"
                self._record_hook_issue(registration, code="hook_timeout", message=error)
                results.append(
                    PluginHookExecutionResult(
                        plugin_id=registration.plugin_id,
                        hook_name=registration.name,
                        phase=registration.phase,
                        status="timeout",
                        elapsed_ms=(perf_counter() - started) * 1000,
                        error=error,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - plugin isolation boundary
                error = str(exc) or exc.__class__.__name__
                self._record_hook_issue(registration, code="hook_failed", message=error)
                results.append(
                    PluginHookExecutionResult(
                        plugin_id=registration.plugin_id,
                        hook_name=registration.name,
                        phase=registration.phase,
                        status="failed",
                        elapsed_ms=(perf_counter() - started) * 1000,
                        error=error,
                    )
                )
        return results

    async def _call_hook_executor(
        self,
        executor: HookExecutor,
        registration: PluginLifecycleHookRegistration,
    ) -> None:
        result = executor(registration)
        if inspect.isawaitable(result):
            await result

    def mark_error(self, plugin_id: str, *, code: str, message: str, phase: str) -> None:
        """Record a plugin-level runtime error without raising to core startup."""
        state = self._states.get(plugin_id)
        if state is None:
            self._states[plugin_id] = PluginRuntimeState(
                plugin_id=plugin_id,
                status=PluginRuntimeStatus.ERROR,
                issues=[
                    PluginRuntimeIssue(
                        plugin_id=plugin_id,
                        code=code,
                        message=message,
                        phase=phase,
                    )
                ],
            )
            return
        state.status = PluginRuntimeStatus.ERROR
        state.issues.append(
            PluginRuntimeIssue(
                plugin_id=plugin_id,
                code=code,
                message=message,
                phase=phase,
            )
        )

    def _register_manifest_resources(self, manifest: PluginManifest) -> None:
        self.resource_ledger.register_manifest_resources(
            plugin_id=manifest.id,
            plugin_version=manifest.version,
            backend_routes=[route.name for route in manifest.routers],
            agents=[agent.id for agent in manifest.agents],
            tools=[tool.name for tool in manifest.tools],
            tool_renderers=[item.id for item in manifest.frontend.tool_renderers],
            file_viewers=[item.id for item in manifest.frontend.file_viewers],
            upload_handlers=[item.id for item in manifest.frontend.upload_handlers],
            skill_importers=[item.id for item in manifest.frontend.skill_importers],
            channel_connectors=[item.id for item in manifest.frontend.channel_connectors],
            message_actions=[item.id for item in manifest.frontend.message_actions],
            chat_input_options=[item.id for item in manifest.frontend.chat_input_options],
            chat_input_panels=[item.id for item in manifest.frontend.chat_input_panels],
            mention_providers=[item.id for item in manifest.frontend.mention_providers],
            welcome_surfaces=[item.id for item in manifest.frontend.welcome_surfaces],
            assistant_identity_resolvers=[
                item.id for item in manifest.frontend.assistant_identity_resolvers
            ],
            agent_categories=[item.id for item in manifest.frontend.agent_categories],
            project_options=[
                f"{manifest.id}.{item.key}" for item in manifest.frontend.project_options
            ],
            session_options=[
                f"{manifest.id}.{item.key}" for item in manifest.frontend.session_options
            ],
            channel_options=[
                f"{manifest.id}.{item.key}" for item in manifest.frontend.channel_options
            ],
            scheduled_task_options=[
                f"{manifest.id}.{item.key}" for item in manifest.frontend.scheduled_task_options
            ],
            permissions=manifest.declared_permissions(),
            settings=[
                (
                    _scoped_setting_resource_id(manifest.id, setting.key, setting.scope),
                    setting.scope,
                )
                for setting in manifest.settings
            ],
            scheduler_jobs=manifest.scheduler_jobs,
            event_listeners=manifest.event_listeners,
            migrations=manifest.migrations,
            frontend_routes=manifest.frontend.routes,
            panels=manifest.frontend.panels,
            nav_items=manifest.frontend.nav_items,
            app_tabs=[item.id for item in manifest.frontend.app_tabs],
            app_panels=[item.id for item in manifest.frontend.app_panels],
            sidebar_items=[item.id for item in manifest.frontend.sidebar_items],
            user_menu_items=[item.id for item in manifest.frontend.user_menu_items],
            i18n_namespaces=manifest.frontend.i18n_namespaces,
            records=[
                PluginResourceRecord(
                    plugin_id=manifest.id,
                    resource_id=resource.id,
                    resource_type=PluginResourceType(resource.type),
                    scope=PluginResourceScope(resource.scope),
                    created_by_plugin_version=manifest.version,
                    retention_policy=PluginResourceRetentionPolicy(resource.retention_policy),
                    cleanup_strategy=PluginResourceCleanupStrategy(resource.cleanup_strategy),
                    metadata=resource.metadata,
                )
                for resource in manifest.resources
            ]
            + _package_resource_records(manifest),
        )

    def _record_hook_issue(
        self,
        registration: PluginLifecycleHookRegistration,
        *,
        code: str,
        message: str,
    ) -> None:
        state = self._states.get(registration.plugin_id)
        if state is None:
            return
        state.status = PluginRuntimeStatus.ERROR
        state.issues.append(
            PluginRuntimeIssue(
                plugin_id=registration.plugin_id,
                code=code,
                message=message,
                phase=registration.phase,
            )
        )

    def _validate_manifest(
        self,
        manifest: PluginManifest,
        *,
        available_dependencies: set[str],
    ) -> list[PluginRuntimeIssue]:
        issues: list[PluginRuntimeIssue] = []
        if manifest.api_version not in self._supported_api_versions:
            issues.append(
                PluginRuntimeIssue(
                    plugin_id=manifest.id,
                    code="unsupported_api_version",
                    message=f"unsupported plugin api version: {manifest.api_version}",
                )
            )

        missing_dependencies = [
            dependency
            for dependency in manifest.depends_on
            if dependency not in available_dependencies
        ]
        if missing_dependencies:
            issues.append(
                PluginRuntimeIssue(
                    plugin_id=manifest.id,
                    code="missing_dependency",
                    message=f"missing plugin dependencies: {', '.join(missing_dependencies)}",
                )
            )

        invalid_permissions = [
            permission
            for permission in manifest.declared_permissions()
            if not _is_namespaced_permission(permission)
        ]
        if invalid_permissions:
            issues.append(
                PluginRuntimeIssue(
                    plugin_id=manifest.id,
                    code="invalid_permission_declaration",
                    message=(
                        "plugin permissions must be namespaced strings: "
                        + ", ".join(invalid_permissions)
                    ),
                )
            )

        invalid_contributions = _invalid_contribution_ids(manifest)
        if invalid_contributions:
            issues.append(
                PluginRuntimeIssue(
                    plugin_id=manifest.id,
                    code="invalid_contribution_namespace",
                    message=(
                        "plugin contribution ids must use the plugin namespace: "
                        + ", ".join(invalid_contributions)
                    ),
                )
            )
        return issues


def _is_namespaced_permission(permission: str) -> bool:
    left, separator, right = permission.partition(":")
    return bool(left.strip() and separator and right.strip())


def _scoped_setting_resource_id(plugin_id: str, key: str, scope: str) -> str:
    if scope == "system":
        return f"{plugin_id}.{key}"
    return f"{plugin_id}.{scope}.{key}"


def _is_plugin_namespaced(value: str, plugin_id: str) -> bool:
    normalized = value.strip()
    if normalized == plugin_id:
        return True
    return normalized.startswith(
        (f"{plugin_id}:", f"{plugin_id}.", f"{plugin_id}-", f"{plugin_id}_")
    )


def _invalid_contribution_ids(manifest: PluginManifest) -> list[str]:
    values: list[str] = []
    values.extend(route.name for route in manifest.routers)
    values.extend(tool.name for tool in manifest.tools)
    allowed_legacy_ids = {
        legacy_id for tool in manifest.tools for legacy_id in tool.legacy_ids if legacy_id.strip()
    }
    values.extend(manifest.frontend.routes)
    values.extend(manifest.frontend.panels)
    values.extend(manifest.frontend.nav_items)
    values.extend(item.id for item in manifest.frontend.app_tabs)
    values.extend(item.id for item in manifest.frontend.app_panels)
    values.extend(item.id for item in manifest.frontend.sidebar_items)
    values.extend(item.id for item in manifest.frontend.user_menu_items)
    values.extend(item.id for item in manifest.frontend.agent_categories)
    values.extend(f"{manifest.id}.{item.key}" for item in manifest.frontend.project_options)
    values.extend(f"{manifest.id}.{item.key}" for item in manifest.frontend.session_options)
    values.extend(f"{manifest.id}.{item.key}" for item in manifest.frontend.channel_options)
    values.extend(f"{manifest.id}.{item.key}" for item in manifest.frontend.scheduled_task_options)
    values.extend(item.id for item in manifest.frontend.tool_renderers)
    values.extend(item.id for item in manifest.frontend.file_viewers)
    values.extend(item.id for item in manifest.frontend.upload_handlers)
    values.extend(item.id for item in manifest.frontend.skill_importers)
    values.extend(item.id for item in manifest.frontend.channel_connectors)
    values.extend(item.id for item in manifest.frontend.message_actions)
    values.extend(item.id for item in manifest.frontend.welcome_surfaces)
    values.extend(item.id for item in manifest.frontend.assistant_identity_resolvers)
    values.extend(manifest.frontend.settings_sections)
    values.extend(manifest.frontend.i18n_namespaces)
    values.extend(manifest.scheduler_jobs)
    values.extend(manifest.event_listeners)
    values.extend(manifest.migrations)
    return [
        value
        for value in values
        if value.strip()
        and value not in allowed_legacy_ids
        and not _is_plugin_namespaced(value, manifest.id)
    ]


def _package_resource_records(manifest: PluginManifest) -> list[PluginResourceRecord]:
    records: list[PluginResourceRecord] = []
    if manifest.package_source_path:
        records.append(
            PluginResourceRecord(
                plugin_id=manifest.id,
                resource_id=manifest.package_source_path,
                resource_type=PluginResourceType.PLUGIN_PACKAGE_FOLDER,
                scope=PluginResourceScope.SYSTEM,
                created_by_plugin_version=manifest.version,
                retention_policy=PluginResourceRetentionPolicy.ARCHIVE_METADATA,
                cleanup_strategy=PluginResourceCleanupStrategy.ARCHIVE,
                metadata={"source_type": manifest.package_source_type},
            )
        )
        if manifest.package_layout.get("has_frontend_dist"):
            frontend_assets = manifest.package_frontend_assets
            records.append(
                PluginResourceRecord(
                    plugin_id=manifest.id,
                    resource_id=f"{manifest.package_source_path}/frontend/dist",
                    resource_type=PluginResourceType.PLUGIN_FRONTEND_ASSET,
                    scope=PluginResourceScope.SYSTEM,
                    created_by_plugin_version=manifest.version,
                    retention_policy=PluginResourceRetentionPolicy.ARCHIVE_METADATA,
                    cleanup_strategy=PluginResourceCleanupStrategy.ARCHIVE,
                    metadata={
                        "asset_mount": f"/plugin-assets/{manifest.id}/",
                        "asset_schema": frontend_assets.asset_schema if frontend_assets else "",
                        "slots": ",".join(frontend_assets.slots) if frontend_assets else "",
                        "asset_count": str(len(frontend_assets.assets)) if frontend_assets else "0",
                    },
                )
            )
    if manifest.package_data_dir:
        records.extend(
            [
                PluginResourceRecord(
                    plugin_id=manifest.id,
                    resource_id=manifest.package_data_dir,
                    resource_type=PluginResourceType.PLUGIN_DATA_FOLDER,
                    scope=PluginResourceScope.SYSTEM,
                    created_by_plugin_version=manifest.version,
                    retention_policy=PluginResourceRetentionPolicy.KEEP_USER_DATA,
                    cleanup_strategy=PluginResourceCleanupStrategy.KEEP,
                    metadata={"data_policy": "plugin-data is retained by default"},
                ),
                PluginResourceRecord(
                    plugin_id=manifest.id,
                    resource_id=f"{manifest.package_data_dir}/config",
                    resource_type=PluginResourceType.PLUGIN_DATA_CONFIG,
                    scope=PluginResourceScope.SYSTEM,
                    created_by_plugin_version=manifest.version,
                    retention_policy=PluginResourceRetentionPolicy.KEEP_USER_DATA,
                    cleanup_strategy=PluginResourceCleanupStrategy.KEEP,
                    metadata={
                        "sensitive_policy": "secrets are stored in plugin_settings, not plain files"
                    },
                ),
                PluginResourceRecord(
                    plugin_id=manifest.id,
                    resource_id=f"{manifest.package_data_dir}/storage",
                    resource_type=PluginResourceType.PLUGIN_DATA_STORAGE,
                    scope=PluginResourceScope.SYSTEM,
                    created_by_plugin_version=manifest.version,
                    retention_policy=PluginResourceRetentionPolicy.KEEP_USER_DATA,
                    cleanup_strategy=PluginResourceCleanupStrategy.KEEP,
                ),
            ]
        )
    return records
