import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("shared page hides feedback and share actions on chat messages", () => {
  const sharedPageSource = readFileSync(
    resolve(__dirname, "../SharedPage.tsx"),
    "utf8",
  );
  const chatMessageSource = readFileSync(
    resolve(__dirname, "../../chat/ChatMessage/index.tsx"),
    "utf8",
  );

  assert.match(sharedPageSource, /showFeedbackAndShareActions=\{false\}/);
  assert.match(chatMessageSource, /showFeedbackAndShareActions\?: boolean/);
  assert.match(
    chatMessageSource,
    /canUseFeedbackAction &&\s*isAuthenticated &&\s*sessionId &&/,
  );
});

test("shared page passes public plugin runtime state into chat messages", () => {
  const sharedPageSource = readFileSync(
    resolve(__dirname, "../SharedPage.tsx"),
    "utf8",
  );

  assert.match(sharedPageSource, /pluginRuntimeApi\.listContributionStates\(\)/);
  assert.match(sharedPageSource, /setRuntimePlugins\(response\.plugins\)/);
  assert.match(sharedPageSource, /runtimePlugins=\{runtimePlugins\}/);
});

test("shared page shows team identity for shared team sessions", () => {
  const sharedPageSource = readFileSync(
    resolve(__dirname, "../SharedPage.tsx"),
    "utf8",
  );

  assert.match(sharedPageSource, /resolveSharedAssistantIdentity/);
  assert.match(sharedPageSource, /sharedAssistant/);
  assert.match(sharedPageSource, /session\.agent_id === "team"/);
  assert.match(sharedPageSource, /data\.session\.team_name/);
  assert.match(sharedPageSource, /personaName=\{sharedAssistant\.name\}/);
  assert.match(sharedPageSource, /personaAvatar=\{sharedAssistant\.avatar\}/);
});
