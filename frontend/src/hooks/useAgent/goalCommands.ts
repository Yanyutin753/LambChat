import type { ActiveGoalSpec } from "./types";

const GOAL_PREFIX_RE = /^\s*\/goal(?:\s+|\n|$)([\s\S]*)$/i;
const SEPARATOR_RE = /^\s*---\s*$/m;

export type FrontendGoalCommand =
  | { action: "run"; goal: ActiveGoalSpec; prompt: string }
  | { action: "persist"; goal: ActiveGoalSpec; prompt: string }
  | { action: "pause" | "resume" }
  | { action: "clear" }
  | { action: "invalid" };

export interface GoalSubmissionPlan {
  content: string;
  goal: ActiveGoalSpec | null;
  nextGoalModeEnabled: boolean;
  nextActiveGoal: ActiveGoalSpec | null;
  handledWithoutSend: boolean;
  errorKey?: string;
}

export function buildDefaultGoalRubric(objective: string): string {
  return [
    `- The final result directly satisfies this objective: ${objective}`,
    "- Every explicit requirement from the user has been addressed.",
    "- The work is verified with the strongest relevant evidence available.",
    "- Any remaining uncertainty, limitation, or skipped verification is clearly reported.",
  ].join("\n");
}

export function parseFrontendGoalCommand(
  message: string,
): FrontendGoalCommand | null {
  const match = GOAL_PREFIX_RE.exec(message || "");
  if (!match) return null;

  const body = match[1]?.trim() || "";
  if (["clear", "reset", "done", "complete"].includes(body.toLowerCase())) {
    return { action: "clear" };
  }
  if (["pause", "resume"].includes(body.toLowerCase())) {
    return { action: body.toLowerCase() as "pause" | "resume" };
  }
  const singleRun = /^run(?:\s|$)/i.test(body);
  const objectiveBody = body.replace(/^(?:persist|run)(?:\s+|$)/i, "");
  if (!objectiveBody) return { action: "invalid" };

  const parts = objectiveBody.split(SEPARATOR_RE);
  const objective = parts[0]?.trim() || "";
  if (!objective) return { action: "invalid" };
  const explicitRubric = parts.slice(1).join("---").trim();
  return {
    action: singleRun ? "run" : "persist",
    goal: buildGoalFromPrompt(objective, explicitRubric),
    prompt: objective,
  };
}

export function buildGoalFromPrompt(
  prompt: string,
  explicitRubric?: string,
): ActiveGoalSpec {
  const objective = prompt.trim();
  return {
    objective,
    rubric: explicitRubric?.trim() || buildDefaultGoalRubric(objective),
    max_iterations: 3,
  };
}

export function planGoalSubmission(
  content: string,
  goalModeEnabled: boolean,
): GoalSubmissionPlan {
  const command = parseFrontendGoalCommand(content);
  if (command?.action === "clear") {
    return {
      content,
      goal: null,
      nextGoalModeEnabled: false,
      nextActiveGoal: null,
      handledWithoutSend: true,
    };
  }
  if (command?.action === "invalid") {
    return {
      content,
      goal: null,
      nextGoalModeEnabled: goalModeEnabled,
      nextActiveGoal: null,
      handledWithoutSend: true,
      errorKey: "chat.goal.required",
    };
  }
  if (command?.action === "run") {
    return {
      content: command.prompt,
      goal: command.goal,
      nextGoalModeEnabled: false,
      nextActiveGoal: command.goal,
      handledWithoutSend: false,
    };
  }
  if (goalModeEnabled) {
    const goal = buildGoalFromPrompt(content);
    return {
      content,
      goal,
      nextGoalModeEnabled: true,
      nextActiveGoal: goal,
      handledWithoutSend: false,
    };
  }
  return {
    content,
    goal: null,
    nextGoalModeEnabled: false,
    nextActiveGoal: null,
    handledWithoutSend: false,
  };
}
