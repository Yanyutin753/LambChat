"""Main-agent Goal controls; authority comes from the bound run, never tool arguments."""

from typing import Literal

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field


class GoalCriterionAudit(BaseModel):
    requirement_id: str = Field(description="Exact requirement ID returned by get_goal")
    evidence_ids: list[str] = Field(
        min_length=1, description="Current original observation IDs proving this requirement"
    )


def create_goal_tools(auditor):
    @tool
    async def get_goal(runtime: ToolRuntime) -> dict:
        """Read this conversation's Goal, full requirements, current turn and usage."""
        return await auditor.get_goal(runtime.state)

    @tool
    async def update_goal(
        status: Literal["complete", "blocked", "paused"],
        explanation: str,
        runtime: ToolRuntime,
        criteria: list[GoalCriterionAudit] | None = None,
    ):
        """Submit a Goal self-audit. Complete only when every requirement is verified;
        call get_goal for required IDs and cite current original evidence for each.
        Blocked reports the same genuine impediment across three consecutive turns;
        keep its explanation stable. Difficulty, slow work and verified waits are not
        blockers. This records a proposal: the host commits it at turn end after
        checking intervening user input and evidence changes. Never create,
        resume or change a Goal here. Use paused ONLY when the user explicitly
        requests pausing this Goal; never pause on your own initiative."""
        audits = [GoalCriterionAudit.model_validate(item).model_dump() for item in criteria or []]
        return await auditor.propose(status, explanation, audits, runtime)

    return [get_goal, update_goal]
