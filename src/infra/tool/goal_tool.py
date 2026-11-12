"""Main-agent Goal controls; authority comes from the bound run, never tool arguments."""

from typing import Literal

from langchain.tools import ToolRuntime, tool


def create_goal_tools(auditor):
    @tool(response_format="content_and_artifact")
    async def get_goal(runtime: ToolRuntime):
        """Read the active Goal and its full completion requirements."""
        goal = await auditor.get_goal(runtime.state)
        if goal.get("error"):
            return goal["error"], goal
        requirements = "\n".join(f"- {item['text']}" for item in goal["requirements"])
        return f"Goal status: {goal['status']}\nCompletion requirements:\n{requirements}", goal

    @tool
    async def update_goal(
        status: Literal["complete", "blocked", "paused"],
        runtime: ToolRuntime,
        explanation: str = "",
    ):
        """Update the active Goal. Complete only when the entire objective is achieved
        and no required work remains. Completion needs only status; no report or evidence
        JSON. For blocked, give one short, stable explanation of the external impediment;
        the host requires the same blocker for three consecutive turns. Slow or difficult
        work and live jobs are not blockers. Paused requires an explicit user request.
        Never resume or change budgets here. Intervening input or changed evidence
        invalidates completion, so address it before reporting completion again."""
        return await auditor.propose(status, explanation, runtime)

    return [get_goal, update_goal]
