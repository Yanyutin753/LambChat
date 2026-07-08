import test from "node:test";
import assert from "node:assert/strict";
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
  assert.match(useAgentTypesSource, /runtimePlugins\?: PluginRuntimeContributionStates/);
  assert.match(useAgentSource, /buildMessageActionContributions/);
  assert.match(useAgentSource, /hydrateMessageActionHistory/);
  assert.match(useAgentSource, /messageActionHistoryContributions/);
  assert.doesNotMatch(useAgentSource, /feedbackApi/);
  assert.doesNotMatch(useAgentSource, /hasMessageActionContribution/);
  assert.doesNotMatch(useAgentSource, /const feedbackPromise/);
  assert.doesNotMatch(useAgentSource, /const feedbackPromise = canReadFeedback/);
  assert.match(historyHydratorSource, /feedbackApi/);
  assert.match(historyHydratorSource, /"feedback\.FeedbackButtons"/);
  assert.match(chatAppContentSource, /useAgent\(\{[\s\S]*runtimePlugins,/);
});
