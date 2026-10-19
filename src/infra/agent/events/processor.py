"""
DeepAgent event processor.

This module keeps the public `AgentEventProcessor` entry point while delegating
the heavier event-specific work to focused helper modules.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from io import StringIO
from typing import Any

from src.infra.agent.events.binary_uploads import upload_binary_blocks
from src.infra.agent.events.buffers import (
    ActivityReferenceFilter,
    ActivityStreamKey,
    BufferKey,
    TextChunkBuffer,
)
from src.infra.agent.events.debug_logger import debug_log_event
from src.infra.agent.events.stream import StreamEventMixin
from src.infra.agent.events.subagents import SubagentEventMixin
from src.infra.agent.events.tool_events import ToolEventMixin
from src.infra.agent.events.tool_outputs import (
    MCP_MEDIA_TYPES,
    MCP_SKIP_KEYS,
    collect_blocks,
    detect_tool_error,
    extract_tool_output,
    get_tool_status,
    normalize_content,
    process_messages,
)
from src.infra.agent.events.types import TOOL_TASK, StreamEvent
from src.infra.agent.first_event_timing import FirstEventTiming
from src.infra.logging import get_logger
from src.infra.pricing.service import compute_partial_usage_cost, compute_usage_cost
from src.infra.writer.present import Presenter
from src.kernel.config import settings

logger = get_logger(__name__)

_CONTEXT_EVENT_TYPES = frozenset(
    (
        "on_chat_model_start",
        "on_chat_model_stream",
        "on_tool_start",
        "on_tool_end",
        "on_tool_error",
    )
)

RUBRIC_GRADER = "rubric_grader"
INTERNAL_STREAM_SOURCES = frozenset(("image_analysis_tool",))
OUTPUT_TEXT_COPY_MAX_CHARS = 8_000


class AgentEventProcessor(SubagentEventMixin, StreamEventMixin, ToolEventMixin):
    """
    Process DeepAgent stream events and forward presenter-ready events.

    The processor is session-scoped. Call `flush()` before reading final output,
    and call `clear()` or `finalize()` when the session is no longer needed.
    Token counters are intentionally retained after `clear()` for existing
    callers that emit usage after stream cleanup.
    """

    __slots__ = (
        "presenter",
        "checkpoint_to_agent",
        "_task_agent_calls",
        "thinking_ids",
        "_output_buffer",
        "total_input_tokens",
        "total_output_tokens",
        "total_tokens",
        "total_cache_creation_tokens",
        "total_cache_read_tokens",
        "_usage_unknown_fields",
        "_usage_observed",
        "_usage_owner",
        "_usage_seeded",
        "_cost_receipts",
        "_legacy_cost_units",
        "_legacy_cost_unknown",
        "_legacy_actual_models",
        "_legacy_model_identity_complete",
        "_usage_ledger_id",
        "_input_includes_cache",
        "_pending_model_runs",
        "_completed_model_runs",
        "_token_usage_emitted",
        "_usage_emit_lock",
        "_usage_duration",
        "_output_buffer_chars",
        "_presenter_emit",
        "_before_tool_start",
        "_base_url",
        "_chunk_buffer",
        "_summary_chunk_buffer",
        "_thinking_chunk_buffer",
        "_tool_args_buffers",
        "_tool_args_meta",
        "_agent_context_cache",
        "_subagent_display_names",
        "_subagent_avatars",
        "_started_tool_call_ids",
        "_rubric_grader_active",
        "_rubric_grader_id",
        "_first_event_timing",
        "_activity_reference_filters",
    )

    _CHUNK_FLUSH_SIZE = 200

    def __init__(
        self,
        presenter: Presenter,
        base_url: str = "",
        subagent_display_names: dict[str, str] | None = None,
        subagent_avatars: dict[str, str] | None = None,
        before_tool_start: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        first_event_timing: FirstEventTiming | None = None,
    ):
        self.presenter = presenter
        owner = getattr(presenter, "_usage_accounting_owner", None)
        self._usage_owner: AgentEventProcessor | None = (
            owner if isinstance(owner, AgentEventProcessor) else None
        )
        self._usage_seeded = False
        self._cost_receipts: dict[str, dict] = {}
        self._legacy_cost_units = 0
        self._legacy_cost_unknown = False
        self._legacy_actual_models: list[dict] = []
        self._legacy_model_identity_complete = True
        self._usage_ledger_id = uuid.uuid4().hex
        if self._usage_owner is None:
            presenter._usage_accounting_owner = self
        self.checkpoint_to_agent: dict[str, tuple[str, str]] = {}
        self._task_agent_calls: dict[str, tuple[str, int]] = {}
        if not base_url:
            base_url = settings.APP_BASE_URL.rstrip("/")
        self._base_url = base_url
        self.thinking_ids: dict[str | None, str | None] = {}
        self._output_buffer = StringIO()
        self._output_buffer_chars = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_tokens = 0
        self.total_cache_creation_tokens = 0
        self.total_cache_read_tokens = 0
        self._usage_unknown_fields: set[str] = set()
        self._usage_observed = False
        self._input_includes_cache = True
        self._pending_model_runs: set[str] = set()
        self._completed_model_runs: set[str] = set()
        self._token_usage_emitted = False
        self._usage_emit_lock = asyncio.Lock()
        self._usage_duration = 0.0
        self._presenter_emit = presenter.emit
        self._before_tool_start = before_tool_start
        chunk_flush_interval = settings.STREAM_CHUNK_FLUSH_INTERVAL
        self._chunk_buffer = TextChunkBuffer(self._CHUNK_FLUSH_SIZE, chunk_flush_interval)
        self._summary_chunk_buffer = TextChunkBuffer(self._CHUNK_FLUSH_SIZE, chunk_flush_interval)
        self._thinking_chunk_buffer = TextChunkBuffer(self._CHUNK_FLUSH_SIZE, chunk_flush_interval)
        self._tool_args_buffers: dict[tuple[str | None, int | str], TextChunkBuffer] = {}
        self._tool_args_meta: dict[tuple[str | None, int | str], tuple[str, str | None]] = {}
        self._activity_reference_filters: dict[
            ActivityStreamKey, tuple[ActivityReferenceFilter, BufferKey]
        ] = {}
        self._agent_context_cache: dict[str, tuple[str | None, int]] = {}
        self._subagent_display_names = subagent_display_names or {}
        self._subagent_avatars = subagent_avatars or {}
        self._started_tool_call_ids: set[str] = set()
        self._rubric_grader_active: bool = False
        self._rubric_grader_id: str | None = None
        self._first_event_timing = first_event_timing or FirstEventTiming()

    @property
    def output_text(self) -> str:
        """Return accumulated top-level assistant output text."""
        return self._output_buffer.getvalue()

    def seed_usage(self, prior_usage: dict | None) -> None:
        """HITL 恢复：把先前分段的累计用量并入计数器。

        恢复分段重新执行节点时计数器从零开始，不 seed 的话最终
        token:usage（以及取 last 落库的 usage_logs）只含最后一段。
        """
        if self._usage_owner is not None:
            self._usage_owner.seed_usage(prior_usage)
            return
        if (
            not isinstance(prior_usage, dict)
            or self._usage_seeded
            or prior_usage.get("_usage_ledger_id") == self._usage_ledger_id
        ):
            return
        fields = {
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cache_creation_tokens",
            "cache_read_tokens",
        }
        if not any(isinstance(prior_usage.get(key), int) for key in fields):
            return
        self._usage_seeded = True
        if prior_usage.get("cost_source") == "provider_settlement":
            self._cost_receipts.update(prior_usage.get("cost_receipts") or {})
            self._legacy_cost_units = prior_usage.get(
                "legacy_cost_units",
                prior_usage.get("cost_units", 0) if not self._cost_receipts else 0,
            )
            self._legacy_cost_unknown = prior_usage.get(
                "legacy_cost_unknown", "cost_receipts" not in prior_usage
            )
            self._legacy_actual_models = prior_usage.get(
                "legacy_actual_models",
                prior_usage.get("actual_models", []) if not self._cost_receipts else [],
            )
        else:
            self._legacy_cost_unknown = True
            # Old trace-wide pricing is an estimate, never evidence of settled spending.
            self._legacy_actual_models = prior_usage.get("actual_models") or []
        self._legacy_model_identity_complete = prior_usage.get(
            "legacy_model_identity_complete",
            prior_usage.get(
                "model_identity_complete",
                bool(self._legacy_actual_models) or bool(self._cost_receipts),
            ),
        )
        self._token_usage_emitted = False
        self._usage_observed = True
        self._input_includes_cache &= prior_usage.get("input_includes_cache") is True
        unknown = prior_usage.get("unknown_usage_fields")
        if isinstance(unknown, list):
            self._usage_unknown_fields.update(
                key for key in unknown if isinstance(key, str) and key in fields
            )
        for field in fields:
            value = prior_usage.get(field)
            if value is None:
                value = 0
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                counter = field if field == "total_tokens" else f"total_{field}"
                setattr(self, counter, getattr(self, counter) + value)
            else:
                self._usage_unknown_fields.add(field)

    def usage_totals(self) -> dict:
        """当前累计用量快照，用于挂起时写入 resume_context 传给下一段。"""
        if self._usage_owner is not None:
            return self._usage_owner.usage_totals()
        totals: dict[str, Any] = {
            "_usage_ledger_id": self._usage_ledger_id,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "cache_creation_tokens": self.total_cache_creation_tokens,
            "cache_read_tokens": self.total_cache_read_tokens,
        }
        if self._usage_observed or self._pending_model_runs:
            totals["usage_observed"] = True
            unknown = self._usage_unknown_fields
            totals["unknown_usage_fields"] = sorted(unknown)
            if self._input_includes_cache:
                totals["input_includes_cache"] = True
        if self._cost_receipts or self._legacy_cost_unknown:
            totals.update(
                cost_source="provider_settlement",
                cost_receipts={key: dict(value) for key, value in self._cost_receipts.items()},
                legacy_cost_units=self._legacy_cost_units,
                legacy_cost_unknown=self._legacy_cost_unknown,
                legacy_actual_models=self._legacy_actual_models,
                legacy_model_identity_complete=self._legacy_model_identity_complete,
            )
        return totals

    def begin_usage_receipt(self, receipt: dict) -> None:
        owner = self._usage_owner or self
        owner._cost_receipts.setdefault(receipt["call_id"], receipt)
        owner._token_usage_emitted = False

    async def record_usage_receipt(self, receipt: dict) -> None:
        if self._usage_owner is not None:
            return await self._usage_owner.record_usage_receipt(receipt)
        previous = self._cost_receipts.get(receipt["call_id"])
        # A completed receipt is immutable; stale partials cannot undo final settlement.
        if previous is not None and (previous == receipt or not previous["unknown"]):
            if not self._token_usage_emitted:
                await self._publish_settlement_usage()
            return
        if previous is not None and receipt["unknown"]:
            receipt = {
                **receipt,
                "charged_units": max(previous["charged_units"], receipt["charged_units"]),
            }
        self._cost_receipts[receipt["call_id"]] = receipt
        self._token_usage_emitted = False
        await self._publish_settlement_usage()

    async def _publish_settlement_usage(self) -> None:
        try:
            await self.emit_token_usage()
        except Exception:
            # Keep the receipt dirty for cleanup; delivery must not retry a paid provider call.
            logger.warning("Failed to publish settled usage receipt", exc_info=True)

    @staticmethod
    def _settlement_usage(snapshot: dict) -> dict | None:
        if snapshot.get("cost_source") != "provider_settlement":
            return None
        receipts = list(snapshot.get("cost_receipts", {}).values())
        models = list(snapshot.get("legacy_actual_models", []))
        for receipt in receipts:
            identity = {key: receipt[key] for key in ("model", "model_id", "provider")}
            if any(identity.values()) and identity not in models:
                models.append(identity)
        return {
            "cost_source": "provider_settlement",
            "cost_units": snapshot.get("legacy_cost_units", 0)
            + sum(item["charged_units"] for item in receipts),
            "cost_complete": not snapshot.get("legacy_cost_unknown", False)
            and all(not item["unknown"] for item in receipts),
            "actual_models": models,
            "model_identity_complete": snapshot.get("legacy_model_identity_complete", True),
            **{
                key: snapshot[key]
                for key in (
                    "cost_receipts",
                    "legacy_cost_units",
                    "legacy_cost_unknown",
                    "legacy_actual_models",
                    "legacy_model_identity_complete",
                )
                if key in snapshot
            },
        }

    async def flush(self) -> None:
        """Flush pending stream chunks without clearing counters or output text."""
        await self._flush_chunk_buffer()
        await self._flush_summary_chunk_buffer()
        await self._flush_thinking_chunk_buffer()
        await self._flush_tool_args_buffers()

    async def drain_activity_references(self) -> None:
        """Finish interrupted streams without clearing their output or usage."""
        for stream_key in list(self._activity_reference_filters):
            await self._finish_activity_reference(stream_key)

    async def finalize(self) -> None:
        """Flush pending chunks and release session-scoped buffers."""
        await self.drain_activity_references()
        await self.flush()
        self.clear()

    async def emit_token_usage(
        self,
        *,
        duration: float = 0.0,
        model_id: str | None = None,
        model: str | None = None,
    ) -> bool:
        """Publish ordered cumulative snapshots, including late cleanup usage."""
        if self._usage_owner is not None:
            return await self._usage_owner.emit_token_usage(
                duration=duration, model_id=model_id, model=model
            )
        async with self._usage_emit_lock:
            return await self._emit_token_usage(duration=duration, model_id=model_id, model=model)

    async def _emit_token_usage(self, *, duration, model_id, model) -> bool:
        if self._token_usage_emitted and duration <= self._usage_duration:
            return False
        duration = max(duration, self._usage_duration)

        config = getattr(self.presenter, "config", None)
        model_id = model_id or getattr(config, "model_id", None)
        model = model or getattr(config, "model", None)

        pending = bool(self._pending_model_runs)
        unknown = self._usage_unknown_fields

        if not (
            self.total_input_tokens > 0
            or self.total_output_tokens > 0
            or self.total_tokens > 0
            or self._usage_observed
            or pending
            or self._cost_receipts
            or self._legacy_cost_unknown
        ):
            return False

        snapshot = self.usage_totals()
        total_tokens = (
            snapshot["total_tokens"] or snapshot["input_tokens"] + snapshot["output_tokens"]
        )
        settlement_usage = self._settlement_usage(snapshot)
        cost, rates = (
            (None, None)
            if settlement_usage is not None
            else await self._resolve_usage_cost(model=model, model_id=model_id, usage=snapshot)
        )
        event = self.presenter.present_token_usage(
            input_tokens=snapshot["input_tokens"],
            output_tokens=snapshot["output_tokens"],
            total_tokens=total_tokens,
            duration=duration,
            cache_creation_tokens=(
                None
                if "cache_creation_tokens" in unknown and not snapshot["cache_creation_tokens"]
                else snapshot["cache_creation_tokens"]
            ),
            cache_read_tokens=(
                None
                if "cache_read_tokens" in unknown and not snapshot["cache_read_tokens"]
                else snapshot["cache_read_tokens"]
            ),
            unknown_usage_fields=sorted(unknown),
            input_includes_cache=snapshot.get("input_includes_cache") is True,
            model_id=model_id,
            model=model,
            cost=cost,
            rates=rates,
            **({"settlement_usage": settlement_usage} if settlement_usage is not None else {}),
        )
        await self._presenter_emit(event)
        self._usage_duration = duration
        # Pricing and delivery can yield while native model ends update the ledger.
        self._token_usage_emitted = snapshot == self.usage_totals()
        return True

    async def _resolve_usage_cost(
        self, *, model: str | None, model_id: str | None, usage: dict
    ) -> tuple[Any, Any]:
        """best-effort 计算本次用量成本；失败或未匹配价格时返回 (None, None)。"""
        if usage.get("input_includes_cache") is not True:
            return None, None
        unknown = set(usage.get("unknown_usage_fields") or [])
        try:
            if not unknown:
                result = await compute_usage_cost(
                    model_value=model,
                    model_config_id=model_id,
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    cache_read_tokens=usage["cache_read_tokens"],
                    cache_creation_tokens=usage["cache_creation_tokens"],
                )
                if result is not None:
                    return result[0], result[1]
            partial_result = await compute_partial_usage_cost(
                model_value=model,
                model_config_id=model_id,
                input_tokens=None if "input_tokens" in unknown else usage["input_tokens"],
                output_tokens=None if "output_tokens" in unknown else usage["output_tokens"],
                cache_read_tokens=None
                if "cache_read_tokens" in unknown
                else usage["cache_read_tokens"],
                cache_creation_tokens=None
                if "cache_creation_tokens" in unknown
                else usage["cache_creation_tokens"],
                input_includes_cache=usage.get("input_includes_cache") is True,
            )
            if partial_result is not None:
                return partial_result[0], partial_result[1]
        except Exception as e:
            logger.debug(f"Pricing: usage cost computation failed: {e}")
        return None, None

    def clear(self) -> None:
        """Release memory held by this session while preserving token counters."""
        self._output_buffer.close()
        self._output_buffer = StringIO()
        self._output_buffer_chars = 0
        self.checkpoint_to_agent.clear()
        self._task_agent_calls.clear()
        self.thinking_ids.clear()
        self._agent_context_cache.clear()
        self._chunk_buffer.reset()
        self._summary_chunk_buffer.reset()
        self._thinking_chunk_buffer.reset()
        self._tool_args_buffers.clear()
        self._tool_args_meta.clear()
        self._activity_reference_filters.clear()
        self._started_tool_call_ids.clear()

    def _track_model_usage(self, event: StreamEvent) -> None:
        kind, run_id = event.get("event"), event.get("run_id")
        if kind in {"on_chat_model_start", "on_chat_model_stream"} and run_id:
            if run_id not in self._completed_model_runs and run_id not in self._pending_model_runs:
                self._pending_model_runs.add(run_id)
                self._token_usage_emitted = False
        elif kind == "on_chat_model_error" and run_id and run_id in self._pending_model_runs:
            self._pending_model_runs.remove(run_id)
            self._completed_model_runs.add(run_id)
            self._mark_unreported_model_usage()
            self._token_usage_emitted = False
        elif kind == "on_chat_model_end" and (
            not run_id or run_id not in self._completed_model_runs
        ):
            if run_id:
                started = run_id in self._pending_model_runs
                self._pending_model_runs.discard(run_id)
                self._completed_model_runs.add(run_id)
                if started and not event.get("data", {}).get("output"):
                    self._mark_unreported_model_usage()
            self._handle_token_usage(event)
            self._token_usage_emitted = False

    async def process_event(self, event: StreamEvent) -> None:
        """Process a single LangChain stream event."""
        # Nested and outer views share native IDs, including streams whose start callback was lost.
        (self._usage_owner or self)._track_model_usage(event)
        if event.get("event") in {"on_chat_model_end", "on_chat_model_error"}:
            await self.emit_token_usage()
        await debug_log_event(event, self._debug_log_context())
        evt_type = event.get("event")
        event_name = event.get("name", "")
        run_id = event.get("run_id")
        if evt_type == "on_chat_model_error":
            return
        if evt_type == "on_custom_event" and event_name == "lambchat_subagent_message":
            await self._handle_subagent_message(event)
            return
        if evt_type == "on_custom_event" and event_name == "lambchat_subagent":
            await self._handle_persistent_subagent_event(event)
            return

        # ── Rubric grader chain detection ──
        # The RubricMiddleware runs a grader sub-agent inside the graph.
        # Detect its chain start/end so we can emit agent:call / agent:result
        # and suppress all internal events to avoid polluting the main stream.
        if event_name == RUBRIC_GRADER:
            match evt_type:
                case "on_chain_start":
                    self._rubric_grader_active = True
                    run_id = event.get("run_id", "")
                    self._rubric_grader_id = f"rubric_grader_{run_id[:8]}"
                    await self._presenter_emit(
                        self.presenter.present_agent_call(
                            agent_id=self._rubric_grader_id,
                            agent_name="Rubric Grader",
                            agent_call_id=run_id or self._rubric_grader_id,
                            input_message="Evaluating against rubric criteria",
                            depth=1,
                        )
                    )
                    return
                case "on_chain_end":
                    sr = self._extract_rubric_result(event)
                    success = sr.get("result", "completed") != "failed"
                    result_text = sr.get("result", "completed")
                    explanation = sr.get("explanation", "")
                    if explanation:
                        result_text = f"{result_text}\n{explanation}"
                    await self._presenter_emit(
                        self.presenter.present_agent_result(
                            agent_id=self._rubric_grader_id or "rubric_grader",
                            agent_call_id=run_id or self._rubric_grader_id,
                            result=result_text,
                            success=success,
                            depth=1,
                        )
                    )
                    self._rubric_grader_active = False
                    self._rubric_grader_id = None
                    return

        tool_name = event_name

        # ask_human is rendered from durable approval events. LangGraph also
        # replays its tool lifecycle around an interrupt; exposing those
        # generic callbacks creates a second, unrelated tool card.
        if tool_name == "ask_human" and evt_type in {
            "on_tool_start",
            "on_tool_end",
            "on_tool_error",
        }:
            return

        if tool_name == TOOL_TASK:
            if event.get("metadata", {}).get("lambchat_managed_task"):
                return
            match evt_type:
                case "on_tool_start":
                    await self._handle_task_start(event)
                    return
                case "on_tool_end":
                    await self._handle_task_end(event)
                    return
                case "on_tool_error":
                    await self._handle_task_error(event)
                    return

        if evt_type == "on_chat_model_end":
            metadata = event.get("metadata", {})
            agent_id = metadata.get("lambchat_subagent_id")
            if not isinstance(agent_id, str) or not agent_id:
                agent_id, _ = self._get_agent_context(self._get_checkpoint_ns(metadata))
            for kind in ("body", "thinking", "summary"):
                await self._finish_activity_reference((agent_id, event.get("run_id"), kind))
            await self.flush()
            self._reset_tool_args_buffers(agent_id)
            return

        if evt_type not in _CONTEXT_EVENT_TYPES:
            return

        # Hide grader internals from the public stream. The chain start/end
        # events above already provide user-visible grading status; routing
        # the internal GraderResponse tool call makes the UI look stuck in a
        # tool loop while the middleware is just validating structured output.
        if self._rubric_grader_active:
            return

        metadata = event.get("metadata", {})
        if self._is_internal_stream_event(metadata):
            return

        checkpoint_ns = None
        checkpoint_ns = self._get_checkpoint_ns(metadata)
        stable_subagent_id = metadata.get("lambchat_subagent_id")
        current_agent_id, current_depth = (
            (stable_subagent_id, 1)
            if isinstance(stable_subagent_id, str) and stable_subagent_id
            else self._get_agent_context(checkpoint_ns)
        )

        if current_depth and logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "[Subagent] %s/%s: agent=%s, depth=%d, ns=%s",
                evt_type,
                tool_name or "N/A",
                current_agent_id,
                current_depth,
                checkpoint_ns[:60] if checkpoint_ns else "N/A",
            )

        match evt_type:
            case "on_chat_model_start":
                run_id = event.get("run_id")
                for stream_key in list(self._activity_reference_filters):
                    if stream_key[0] == current_agent_id and stream_key[1] != run_id:
                        await self._finish_activity_reference(stream_key)
                # 新模型流开始：上一步残留的参数缓冲已被 model_end 冲掉，
                # 异常中断的残留在此丢弃（对应工具不会执行）。
                self._reset_tool_args_buffers(current_agent_id)
                if current_depth == 0:
                    self._first_event_timing.start_model()
            case "on_chat_model_stream":
                if self._get_lc_source(metadata) == "summarization":
                    await self._handle_summary_stream(event, current_agent_id, current_depth)
                else:
                    if current_depth == 0:
                        self._record_first_stream_milestones(event)
                    await self._handle_chat_stream(event, current_agent_id, current_depth)
            case "on_tool_start":
                await self.flush()
                await self._handle_tool_start(event, tool_name, current_agent_id, current_depth)
            case "on_tool_end":
                await self.flush()
                await self._handle_tool_end(event, tool_name, current_agent_id, current_depth)
            case "on_tool_error":
                await self.flush()
                await self._handle_tool_error(event, tool_name, current_agent_id, current_depth)

    _extract_tool_output = staticmethod(extract_tool_output)
    _detect_tool_error = staticmethod(detect_tool_error)
    _get_tool_status = staticmethod(get_tool_status)
    _collect_blocks = staticmethod(collect_blocks)
    _normalize_content = staticmethod(normalize_content)
    _process_messages = staticmethod(process_messages)
    _MCP_MEDIA_TYPES = MCP_MEDIA_TYPES
    _MCP_SKIP_KEYS = MCP_SKIP_KEYS

    def _debug_log_context(self) -> dict[str, Any]:
        """Return LambChat run identity for raw stream-event debug logs."""
        config = getattr(self.presenter, "config", None)
        return {
            "trace_id": getattr(self.presenter, "trace_id", None),
            "run_id": getattr(self.presenter, "run_id", None),
            "session_id": getattr(config, "session_id", None),
            "agent_id": getattr(config, "agent_id", None),
            "agent_name": getattr(config, "agent_name", None),
        }

    def _record_first_stream_milestones(self, event: StreamEvent) -> None:
        chunk = event.get("data", {}).get("chunk")
        if chunk is None:
            return

        self._first_event_timing.record_once("provider_first_delta")
        content = getattr(chunk, "content", None)
        if isinstance(content, str):
            if content:
                self._first_event_timing.record_once("provider_first_text")
                return
            reasoning = getattr(chunk, "additional_kwargs", {}).get("reasoning_content")
            if reasoning:
                self._first_event_timing.record_once("provider_first_reasoning")
            return

        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type in ("thinking", "reasoning") and (
                block.get("thinking") or block.get("reasoning")
            ):
                self._first_event_timing.record_once("provider_first_reasoning")
            elif block_type == "text" and block.get("text"):
                self._first_event_timing.record_once("provider_first_text")

    @staticmethod
    def _is_internal_stream_event(metadata: dict[str, Any]) -> bool:
        source = metadata.get("lc_source") or metadata.get("source")
        return bool(metadata.get("internal_tool_call") or source in INTERNAL_STREAM_SOURCES)

    async def _upload_binary_blocks(self, result: dict) -> None:
        await upload_binary_blocks(result, self._base_url)

    @staticmethod
    def _extract_rubric_result(event: StreamEvent) -> dict:
        """Extract the structured rubric evaluation from a grader chain-end event."""
        output: Any = event.get("data", {}).get("output", {})
        if not isinstance(output, dict):
            return {}
        sr = output.get("structured_response")
        if sr is None:
            return {}
        if isinstance(sr, dict):
            return sr
        # Pydantic model or similar object
        return {k: getattr(sr, k, "") for k in ("result", "explanation", "criteria")}


__all__ = ["AgentEventProcessor", "INTERNAL_STREAM_SOURCES", "StreamEvent"]
