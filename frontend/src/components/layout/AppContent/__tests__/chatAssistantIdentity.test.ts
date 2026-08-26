import { resolveChatAssistantIdentity } from "../ChatViewProps";
import type { Team } from "../../../../types/team";

const baseArgs = {
  currentAgent: "deepagents",
  currentPersonaAvatar: null,
  currentTeam: null,
  selectedPersonaName: null,
};

test("falls back to agent display name when no persona name selected", () => {
  expect(
    resolveChatAssistantIdentity({
      ...baseArgs,
      agentDisplayName: "Deep Agent",
    }).name,
  ).toBe("Deep Agent");
});

test("persona name still takes priority over agent display name", () => {
  expect(
    resolveChatAssistantIdentity({
      ...baseArgs,
      selectedPersonaName: "小羊",
      agentDisplayName: "Deep Agent",
    }).name,
  ).toBe("小羊");
});

test("returns null name when neither persona nor agent display name given", () => {
  expect(resolveChatAssistantIdentity(baseArgs).name).toBeNull();
});

test("team mode still resolves team name and ignores agent display name", () => {
  const team = {
    id: "t1",
    name: "梦之队",
    members: [],
    default_member_id: null,
  } as unknown as Team;
  expect(
    resolveChatAssistantIdentity({
      ...baseArgs,
      currentAgent: "team",
      currentTeam: team,
      agentDisplayName: "Deep Agent",
    }).name,
  ).toBe("梦之队");
});

test("blank agent display name is ignored", () => {
  expect(
    resolveChatAssistantIdentity({
      ...baseArgs,
      agentDisplayName: "  ",
    }).name,
  ).toBeNull();
});
