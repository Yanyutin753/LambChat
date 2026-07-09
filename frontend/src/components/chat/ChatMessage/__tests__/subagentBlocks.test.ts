import {
  buildSubagentPanelState,
  getSubagentAvatarImageUrl,
  getSubagentRoleIconMeta,
} from "../SubagentBlocks.tsx";

test("subagent panel subtitle shows only the start time", () => {
  const startedAt = Date.UTC(2026, 4, 10, 1, 45, 54);
  const completedAt = startedAt + 26_076 * 60_000 + 2_000;

  const state = buildSubagentPanelState({
    agentId: "agent-a",
    agentName: "worker_agent",
    input: "Do work",
    status: "complete",
    startedAt,
    completedAt,
  });

  expect(state.subtitle).toBe(
    new Date(startedAt).toLocaleString(undefined, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }),
  );
  expect(!state.subtitle?.includes(" · ")).toBeTruthy();
  expect(!state.subtitle?.includes("26076m 2s")).toBeTruthy();
});

test("subagent role icon meta matches recognizable role names", () => {
  expect(getSubagentRoleIconMeta("设计理念分析").kind).toBe("design");
  expect(getSubagentRoleIconMeta("frontend_code_reviewer").kind).toBe("code");
  expect(getSubagentRoleIconMeta("qa test analyst").kind).toBe("test");
  expect(getSubagentRoleIconMeta("general-purpose").kind).toBe("general");
});

test("subagent avatar image url accepts role url and emoji avatars", () => {
  expect(getSubagentAvatarImageUrl("/api/files/avatar.png")).toBe(
    "/api/files/avatar.png",
  );
  expect(getSubagentAvatarImageUrl("🎨") || "").toMatch(/fluent-emoji/);
  expect(getSubagentAvatarImageUrl("icon:writing")).toBe(null);
});
