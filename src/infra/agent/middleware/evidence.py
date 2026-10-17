"""Keep tool-result references outside the compressible message channel."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Annotated, Any, NotRequired

from langchain.agents.middleware.types import AgentMiddleware, AgentState, PrivateStateAttr
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command

from src.infra.agent.events.tool_outputs import detect_tool_error
from src.infra.agent.evidence import (
    content_sha256,
    evidence_directory,
    evidence_index,
    evidence_read_text,
    evidence_scope,
    merge_evidence,
    verified_original_content,
)

logger = logging.getLogger(__name__)


@dataclass
class EvidenceClock:
    """Shared by a run's parent and children; fresh recovery tokens fence old proof."""

    token: str = field(default_factory=lambda: uuid.uuid4().hex)
    generation: int = 0
    active_writes: int = 0

    def current(self, record: dict) -> bool:
        return (
            self.active_writes == 0
            and record.get("evidence_clock_token") == self.token
            and record.get("evidence_clock_generation") == self.generation
        )

    def invalidate_old(self, records: list[dict]) -> list[dict]:
        return [
            {
                **item,
                "status": "stale",
                "invalidation_reason": "Workspace inputs changed or execution ownership was restored; obtain a fresh observation",
            }
            if item.get("status") in {"observed", "verified"} and not self.current(item)
            else item
            for item in records
        ]


class EvidenceState(AgentState):
    evidence: NotRequired[Annotated[list[dict[str, Any]], PrivateStateAttr, merge_evidence]]
    _evidence_scope_version: NotRequired[Annotated[str, PrivateStateAttr]]
    _evidence_clock_token: NotRequired[Annotated[str, PrivateStateAttr]]
    _evidence_clock_generation: NotRequired[Annotated[int, PrivateStateAttr]]


class EvidenceMiddleware(AgentMiddleware):
    state_schema = EvidenceState

    def __init__(
        self,
        *,
        session_id: str,
        run_id: str,
        scope_version: str,
        backend: Any = None,
        writer: Any = None,
        clock: EvidenceClock | None = None,
    ):
        self.session_id = session_id
        self.run_id = run_id
        self.scope_version = scope_version
        self.backend = backend
        self.writer = writer or self._write
        self.clock = clock or EvidenceClock()
        self._source_lock = asyncio.Lock()

    def before_agent(self, state, runtime):
        return {
            "_evidence_scope_version": self.scope_version,
            "_evidence_clock_token": self.clock.token,
            "_evidence_clock_generation": self.clock.generation,
            "evidence": self.clock.invalidate_old(state.get("evidence", [])),
        }

    async def _write(self, record: dict, content: Any) -> str | None:
        path = f"{evidence_directory(self.backend)}/{record['evidence_id']}.json"
        async with self._source_lock:
            try:
                try:
                    existing = await self.backend.aread(path)
                except FileNotFoundError:
                    existing = None
                if existing is not None:
                    error = getattr(existing, "error", None)
                    if not error:
                        verified_original_content(evidence_read_text(existing), record)
                        return path
                    if not any(
                        marker in str(error).lower()
                        for marker in (
                            "not found",
                            "does not exist",
                            "no such file",
                            "enoent",
                            "file_not_found",
                        )
                    ):
                        raise ValueError("Existing evidence could not be checked")
                payload = json.dumps(
                    {"observation": record, "content": content}, ensure_ascii=False, default=str
                )
                written = await self.backend.awrite(path, payload)
                # Re-read also handles a backend refusing an already-existing file
                # during replay. A generic backend offers no atomic create-only API.
                original = await self.backend.aread(path)
                verified_original_content(evidence_read_text(original), record)
                if getattr(written, "error", None):
                    logger.debug("Evidence write reused a matching existing observation")
                return path
            except Exception:
                logger.warning("Evidence original could not be preserved", exc_info=True)
                return None

    async def abefore_model(self, state, runtime):
        records = self.clock.invalidate_old(state.get("evidence", []))
        index = evidence_index(records, self.scope_version)
        update: dict[str, Any] = {"evidence": records}
        content = (
            "System-recorded evidence snapshot. The latest snapshot supersedes earlier indexes.\n\n"
            "Internal evidence metadata; this does not start a user or Goal turn. "
            "Only the original turn_context determines continuation.turn.\n\n" + index
        )
        previous = next(
            (
                message
                for message in reversed(state.get("messages", []))
                if isinstance(message, HumanMessage) and message.name == "evidence_context"
            ),
            None,
        )
        # Checkpoint updates append before dispatch; changing the system prefix loses history caches.
        if index and (previous is None or previous.content != content):
            update["messages"] = [
                HumanMessage(
                    content=content,
                    name="evidence_context",
                    additional_kwargs={"lambchat_evidence_snapshot": True},
                )
            ]
        return update

    async def awrap_tool_call(self, request, handler):
        call = request.tool_call
        state = getattr(request, "state", {})
        records = self.clock.invalidate_old(state.get("evidence", []))
        state["evidence"] = records
        mutating = call["name"] in {
            "write_file",
            "edit_file",
            "execute",
            "execute_command",
            "apply_patch",
            "transfer_file",
            "transfer_path",
            "delete_file",
            "move_file",
            "copy_file",
            "env_var_set",
            "env_var_delete",
            "env_var_delete_all",
        }
        if mutating:
            self.clock.active_writes += 1
            self.clock.generation += 1
            records = [
                {
                    **item,
                    "status": "stale",
                    "invalidation_reason": f"Inputs may change during {call['name']}; revalidate before relying on prior proof",
                }
                for item in state.get("evidence", [])
            ]
            # Make concurrent graders/readers see invalidation before the write begins.
            state["evidence"] = records
        generation = self.clock.generation
        raised = None
        try:
            result = await handler(request)
        except (Exception, asyncio.CancelledError) as exc:
            from langgraph.errors import GraphInterrupt

            if isinstance(exc, GraphInterrupt):
                raise
            raised = exc
            result = ToolMessage(
                content="Tool cancelled"
                if isinstance(exc, asyncio.CancelledError)
                else f"Tool failed: {exc}",
                tool_call_id=call["id"],
                status="error",
            )
        finally:
            if mutating:
                self.clock.active_writes -= 1
                self.clock.generation += 1
                generation = self.clock.generation
        update = (
            dict(result.update or {})
            if isinstance(result, Command) and isinstance(result.update, dict)
            else {}
        )
        messages = update.get("messages", []) if isinstance(result, Command) else [result]
        message = next((m for m in messages if isinstance(m, ToolMessage)), None)
        if message is None or message.additional_kwargs.get("lambchat_subagent_unchanged"):
            return result
        raw = message.content
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                pass
        failed = detect_tool_error(message, raw)[0] or (
            isinstance(raw, dict)
            and (
                raw.get("success") is False
                or raw.get("ok") is False
                or raw.get("isError") is True
                or bool(raw.get("error"))
            )
        )
        original_content = message.additional_kwargs.get(
            "lambchat_original_content", message.content
        )
        record = {
            "content_sha256": content_sha256(original_content),
            "evidence_id": hashlib.sha256(
                f"{self.session_id}:{self.run_id}:{self.clock.token}:{generation}:{call['id']}".encode()
            ).hexdigest()[:32],
            "evidence_clock_token": self.clock.token,
            "evidence_clock_generation": generation,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "tool_call_id": call["id"],
            "event_id": call["id"],
            "claim": f"Tool observation: {call['name']}",
            "criterion": "",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "scope_version": self.scope_version,
            "status": "unavailable" if failed else "observed",
            "source_ref": "",
        }
        try:
            record["source_ref"] = await self.writer(record, original_content) or ""
        except Exception:
            logger.warning("Evidence persistence failed", exc_info=True)
        if not record["source_ref"]:
            record["status"] = "unavailable"
        if generation != self.clock.generation and record["status"] == "observed":
            record["status"] = "stale"
            record["invalidation_reason"] = (
                "Inputs changed while this observation was in flight; revalidate"
            )
        child_records = []
        if call["name"] in {"task", "wait_subagent", "send_subagent_message"}:
            child_records = [
                item
                for item in message.additional_kwargs.get("lambchat_subagent_evidence", [])
                if isinstance(item, dict)
                and item.get("session_id") == self.session_id
                and item.get("scope_version") == self.scope_version
            ]
        child_records = self.clock.invalidate_old(child_records)
        update["evidence"] = self.clock.invalidate_old([*records, *child_records, record])
        if raised is not None:
            state["evidence"] = merge_evidence(state.get("evidence", []), update["evidence"])
            raise raised
        if not isinstance(result, Command):
            update["messages"] = [message]
            return Command(update=update)
        return Command(update=update, goto=result.goto, resume=result.resume, graph=result.graph)


def create_evidence_middleware(
    *,
    backend: Any,
    session_id: str,
    presenter: Any,
    active_goal: dict | None = None,
    clock: EvidenceClock | None = None,
) -> EvidenceMiddleware:
    scope = evidence_scope(active_goal)
    return EvidenceMiddleware(
        backend=backend,
        session_id=session_id,
        run_id=str(getattr(presenter, "run_id", "") or ""),
        scope_version=scope,
        clock=clock,
    )
