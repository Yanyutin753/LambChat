import {
  buildDefaultGoalRubric,
  buildGoalFromPrompt,
  planGoalSubmission,
  parseFrontendGoalCommand,
} from "../goalCommands.ts";

test("parses frontend inline goal command as run prompt and goal", () => {
  const command = parseFrontendGoalCommand("/goal finish docs");

  expect(command).toEqual({
    action: "run",
    prompt: "finish docs",
    goal: {
      objective: "finish docs",
      rubric: buildDefaultGoalRubric("finish docs"),
      max_iterations: 3,
    },
  });
});

test("parses frontend inline goal command with explicit rubric", () => {
  const command = parseFrontendGoalCommand(
    "/goal finish docs\n---\n- docs updated\n- tests pass",
  );

  expect(command).toEqual({
    action: "run",
    prompt: "finish docs",
    goal: {
      objective: "finish docs",
      rubric: "- docs updated\n- tests pass",
      max_iterations: 3,
    },
  });
});

test("parses frontend goal clear command", () => {
  expect(parseFrontendGoalCommand("/goal clear")).toEqual({
    action: "clear",
  });
});

test("treats bare goal command as invalid", () => {
  expect(parseFrontendGoalCommand("/goal")).toEqual({
    action: "invalid",
  });
});

test("ignores normal messages", () => {
  expect(parseFrontendGoalCommand("please continue")).toBe(null);
});

test("builds a goal from a normal prompt for goal mode", () => {
  expect(buildGoalFromPrompt("please continue")).toEqual({
    objective: "please continue",
    rubric: buildDefaultGoalRubric("please continue"),
    max_iterations: 3,
  });
});

test("plans inline goal command as one run-scoped send with stripped prompt and goal", () => {
  const plan = planGoalSubmission("/goal finish docs", false);

  expect(plan).toEqual({
    content: "finish docs",
    goal: {
      objective: "finish docs",
      rubric: buildDefaultGoalRubric("finish docs"),
      max_iterations: 3,
    },
    nextGoalModeEnabled: false,
    nextActiveGoal: {
      objective: "finish docs",
      rubric: buildDefaultGoalRubric("finish docs"),
      max_iterations: 3,
    },
    handledWithoutSend: false,
  });
});

test("plans normal messages in goal mode as prompt and run goal", () => {
  const plan = planGoalSubmission("continue implementation", true);

  expect(plan).toEqual({
    content: "continue implementation",
    goal: {
      objective: "continue implementation",
      rubric: buildDefaultGoalRubric("continue implementation"),
      max_iterations: 3,
    },
    nextGoalModeEnabled: true,
    nextActiveGoal: {
      objective: "continue implementation",
      rubric: buildDefaultGoalRubric("continue implementation"),
      max_iterations: 3,
    },
    handledWithoutSend: false,
  });
});

test("plans goal clear as local-only frontend cleanup", () => {
  const plan = planGoalSubmission("/goal clear", true);

  expect(plan).toEqual({
    content: "/goal clear",
    goal: null,
    nextGoalModeEnabled: false,
    nextActiveGoal: null,
    handledWithoutSend: true,
  });
});

test("plans bare goal command as invalid local-only action", () => {
  const plan = planGoalSubmission("/goal", false);

  expect(plan).toEqual({
    content: "/goal",
    goal: null,
    nextGoalModeEnabled: false,
    nextActiveGoal: null,
    handledWithoutSend: true,
    errorKey: "chat.goal.required",
  });
});

test("persistent goal commands stay distinct from run-scoped goals", () => {
  expect(parseFrontendGoalCommand("/goal persist finish docs\n---\n- docs verified")).toEqual({
    action: "persist",
    goal: { objective: "finish docs", rubric: "- docs verified", max_iterations: 3 },
    prompt: "finish docs",
  });
  expect(parseFrontendGoalCommand("/goal pause")).toEqual({ action: "pause" });
  expect(parseFrontendGoalCommand("/goal resume")).toEqual({ action: "resume" });
  expect(parseFrontendGoalCommand("/goal persist")).toEqual({ action: "invalid" });
});
