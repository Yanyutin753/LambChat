"""Persistent Goals use the main agent's evidence-backed audit, without another LLM."""

from typing import Annotated, Any, NotRequired

from deepagents.middleware.rubric import RubricMiddleware, RubricState
from langchain.agents.middleware.types import PrivateStateAttr
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from src.infra.agent.evidence import evidence_scope
from src.infra.tool.goal_tool import create_goal_tools


async def audit_has_pending_input(session_id, applied_ids):
    from src.infra.task.steer import get_steer_queue

    queue = get_steer_queue()
    if await queue.list_items(session_id):
        return True
    return any(item.id not in applied_ids for item in await queue.list_receipts(session_id))


class GoalAuditState(RubricState):
    _goal_audit: NotRequired[Annotated[dict[str, Any], PrivateStateAttr]]


class GoalSelfAuditMiddleware(RubricMiddleware):
    state_schema = GoalAuditState

    @property
    def name(self):
        # Old checkpoints can resume at either rubric hook; keep their node identities.
        return "_RetryableRubricMiddleware"

    def __init__(self, *, model, goal, presenter, backend, session_id, user_id, evidence_clock):
        super().__init__(model=model, max_iterations=1)
        self.goal = goal
        self.presenter = presenter
        self.backend = backend
        self.session_id = session_id
        self.user_id = user_id
        self.clock = evidence_clock
        self.tools = create_goal_tools(self)

    async def current_goal(self):
        from src.infra.persistent_goal import GoalService

        current = await GoalService().get(self.session_id, self.user_id)
        if (
            current is None
            or current.id != self.goal["_persistent_id"]
            or current.version != self.goal["_persistent_version"]
            or current.current_run_id != self.presenter.run_id
            or current.status != "active"
        ):
            return None
        return current

    def requirements(self, current, state):
        texts = [
            current.objective,
            *[line.strip() for line in current.rubric.splitlines() if line.strip()],
        ]
        # Preserve criterion names frozen by an old checkpoint's independent grader.
        if state.get("_active_rubric") == current.rubric:
            texts.extend(item for item in state.get("_rubric_criteria", []) if item not in texts)
        return [{"id": f"r{index}", "text": text} for index, text in enumerate(texts)]

    async def get_goal(self, state):
        current = await self.current_goal()
        if current is None:
            return {"status": "error", "error": "Goal is paused, superseded or outside this run"}
        return {
            "status": current.status,
            "objective": current.objective,
            "rubric": current.rubric,
            "requirements": self.requirements(current, state),
            "turn": current.accounting.turns + 1,
            "tokens_used": current.accounting.tokens,
            "previous_audit": current.last_verdict,
            "blocked_turns": current.blocked_turns,
        }

    async def propose(self, status, explanation, runtime):
        from src.infra.agent.evidence import load_grader_evidence

        current = await self.current_goal()
        if current is None:
            return {"status": "error", "error": "Goal is paused, superseded or outside this run"}
        if status == "blocked" and not explanation.strip():
            return {
                "status": "error",
                "error": "Give one short explanation of the external blocker",
            }
        ready: set[str] = set()
        snapshot = (self.clock.token, self.clock.generation)
        if status == "complete":
            if self.backend is not None:
                _, ready = await load_grader_evidence(
                    runtime.state.get("evidence", []),
                    backend=self.backend,
                    session_id=self.session_id,
                    scope_version=evidence_scope(self.goal),
                    current_clock=self.clock,
                )
            if not ready:
                return {
                    "status": "error",
                    "error": "Verify the result with current readable original evidence before completing",
                }
        audit = {
            "result": "satisfied" if status == "complete" else status,
            "explanation": explanation.strip(),
        }
        if status == "complete":
            audit["self_audit"] = True
            audit["evidence_ids"] = sorted(ready)
        return Command(
            update={
                "_goal_audit": {
                    "verdict": audit,
                    "goal_id": current.id,
                    "version": current.version,
                    "run_id": current.current_run_id,
                    "clock": list(snapshot),
                    "tool_call_id": runtime.tool_call_id,
                    "steer_ids": sorted(runtime.state.get("_steer_applied", {})),
                    "evidence_ids": sorted(ready),
                },
                "messages": [
                    ToolMessage(
                        content="Self-audit recorded for turn-end validation. Stop only if all requested work is done; intervening input or changed evidence requires a new audit."
                        if status == "complete"
                        else "Requested pause recorded. Stop Goal work and report the pause; the host commits it at turn end."
                        if status == "paused"
                        else "Blocker recorded. The host stops only after the same blocker persists for three consecutive turns.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    def before_agent(self, state, runtime):
        return None

    async def abefore_agent(self, state, runtime):
        return None

    def after_agent(self, state, runtime):
        # The application executes async graphs; never revive legacy synchronous grading.
        return None

    async def aafter_agent(self, state, runtime):
        self.presenter.goal_audit_steer_ids = sorted(state.get("_steer_applied", {}))
        self.presenter.goal_evidence_ready = False
        self.presenter.goal_evidence_ids = []
        self.presenter.goal_verdict = {
            "result": "needs_revision",
            "explanation": "Continue the full goal and submit update_goal only after a current self-audit.",
        }
        audit = state.get("_goal_audit") or {}
        latest_call = next(
            (
                call["id"]
                for message in reversed(state.get("messages", []))
                if isinstance(message, AIMessage)
                for call in reversed(message.tool_calls)
                if call["name"] == "update_goal"
            ),
            audit.get("tool_call_id"),
        )
        current = await self.current_goal()
        if (
            latest_call != audit.get("tool_call_id")
            or current is None
            or audit.get("goal_id") != current.id
            or audit.get("version") != current.version
            or audit.get("run_id") != current.current_run_id
            or (
                audit.get("verdict", {}).get("result") != "paused"
                and (
                    audit.get("clock") != [self.clock.token, self.clock.generation]
                    or self.clock.active_writes
                )
            )
            or audit.get("steer_ids") != sorted(state.get("_steer_applied", {}))
        ):
            return None
        self.presenter.goal_verdict = audit["verdict"]
        self.presenter.goal_evidence_ids = audit["evidence_ids"]
        self.presenter.goal_evidence_ready = bool(audit["evidence_ids"])
        self.presenter.goal_evidence_clock = self.clock
        self.presenter.goal_evidence_clock_snapshot = (self.clock.token, self.clock.generation)
        return None
