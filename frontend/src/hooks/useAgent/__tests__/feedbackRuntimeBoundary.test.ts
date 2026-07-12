import { readFileSync } from "node:fs";

const useAgentSource = readFileSync(
  new URL("../../useAgent.ts", import.meta.url),
  "utf8",
);
const useAgentTypesSource = readFileSync(
  new URL("../types.ts", import.meta.url),
  "utf8",
);
const chatAppContentSource = readFileSync(
  new URL("../../../components/layout/AppContent/ChatAppContent.tsx", import.meta.url),
  "utf8",
);
const historyHydratorSource = readFileSync(
  new URL("../../../components/chat/ChatMessage/messageActionHistoryHydrators.ts", import.meta.url),
  "utf8",
);

test("Feedback history hydration follows the plugin message-action contribution", () => {
  expect(useAgentTypesSource).toMatch(/runtimePlugins\?: PluginRuntimeContributionStates/);
  expect(useAgentSource).toMatch(/buildMessageActionContributions/);
  expect(useAgentSource).toMatch(/hydrateMessageActionHistory/);
  expect(useAgentSource).toMatch(/messageActionHistoryContributions/);
  expect(useAgentSource).not.toMatch(/feedbackApi/);
  expect(useAgentSource).not.toMatch(/hasMessageActionContribution/);
  expect(useAgentSource).not.toMatch(/const feedbackPromise/);
  expect(useAgentSource).not.toMatch(/const feedbackPromise = canReadFeedback/);
  expect(historyHydratorSource).toMatch(/feedbackApi/);
  expect(historyHydratorSource).toMatch(/"feedback\.FeedbackButtons"/);
  expect(chatAppContentSource).toMatch(/useAgent\(\{[\s\S]*runtimePlugins,/);
});
