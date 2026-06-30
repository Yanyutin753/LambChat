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
  const messageActionRenderersSource = readFileSync(
    resolve(__dirname, "../../chat/ChatMessage/messageActionRenderers.tsx"),
    "utf8",
  );

  assert.match(sharedPageSource, /showFeedbackAndShareActions=\{false\}/);
  assert.match(chatMessageSource, /showFeedbackAndShareActions\?: boolean/);
  assert.match(chatMessageSource, /buildMessageActionContributions\(runtimePlugins, \{/);
  assert.match(chatMessageSource, /target: "assistant_message"/);
  assert.match(chatMessageSource, /MESSAGE_ACTION_RENDERERS/);
  assert.doesNotMatch(chatMessageSource, /FeedbackButtons/);
  assert.match(messageActionRenderersSource, /FeedbackButtons/);
  assert.match(chatMessageSource, /isAuthenticated &&\s*sessionId &&/);
  assert.doesNotMatch(chatMessageSource, /canUseFeedbackAction/);
});

test("shared page passes public plugin runtime state into chat messages", () => {
  const sharedPageSource = readFileSync(
    resolve(__dirname, "../SharedPage.tsx"),
    "utf8",
  );

  assert.match(sharedPageSource, /useExtensionContributions/);
  assert.match(sharedPageSource, /const EMPTY_RUNTIME_PLUGINS/);
  assert.match(
    sharedPageSource,
    /extensionContributions\?\.plugins \?\? EMPTY_RUNTIME_PLUGINS/,
  );
  assert.match(sharedPageSource, /runtimePlugins=\{runtimePlugins\}/);
  assert.doesNotMatch(sharedPageSource, /pluginRuntimeApi\.listContributions\(\)/);
  assert.doesNotMatch(sharedPageSource, /setRuntimePlugins/);
});

test("shared page shows team identity for shared team sessions", () => {
  const sharedPageSource = readFileSync(
    resolve(__dirname, "../SharedPage.tsx"),
    "utf8",
  );
  const assistantIdentitySource = readFileSync(
    resolve(__dirname, "../../chat/chatAssistantIdentityResolvers.ts"),
    "utf8",
  );

  assert.match(sharedPageSource, /resolveSharedAssistantIdentity/);
  assert.match(sharedPageSource, /resolveSharedPluginAssistantIdentity/);
  assert.match(sharedPageSource, /resolvePluginAssistantIdentitySnapshot/);
  assert.match(sharedPageSource, /sharedAssistant/);
  assert.match(sharedPageSource, /sharedPluginAssistant/);
  assert.doesNotMatch(sharedPageSource, /session\.agent_id === "team"/);
  assert.match(assistantIdentitySource, /buildAssistantIdentityResolverContributions/);
  assert.match(assistantIdentitySource, /agent_team\.TeamAssistantIdentity/);
  assert.doesNotMatch(sharedPageSource, /\{data\.session\.team_name\}/);
  assert.match(sharedPageSource, /\{sharedPluginAssistant\.name\}/);
  assert.match(sharedPageSource, /personaName=\{sharedAssistant\.name\}/);
  assert.match(sharedPageSource, /personaAvatar=\{sharedAssistant\.avatar\}/);
});

test("share dialog supports editing existing shares without replacing the public link", () => {
  const shareDialogSource = readFileSync(
    resolve(__dirname, "../ShareDialog.tsx"),
    "utf8",
  );
  const shareApiSource = readFileSync(
    resolve(__dirname, "../../../services/api/share.ts"),
    "utf8",
  );

  assert.match(shareApiSource, /async update\(/);
  assert.match(shareApiSource, /method: "PATCH"/);
  assert.match(shareDialogSource, /editingShare/);
  assert.match(shareDialogSource, /handleEditShare/);
  assert.match(shareDialogSource, /handleSaveShare/);
  assert.match(shareDialogSource, /share\.saveShare/);
});
