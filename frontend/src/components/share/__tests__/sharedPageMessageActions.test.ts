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

  expect(sharedPageSource).toMatch(/showFeedbackAndShareActions=\{false\}/);
  expect(chatMessageSource).toMatch(/showFeedbackAndShareActions\?: boolean/);
  expect(chatMessageSource).toMatch(/buildMessageActionContributions\(runtimePlugins, \{/);
  expect(chatMessageSource).toMatch(/target: "assistant_message"/);
  expect(chatMessageSource).toMatch(/MESSAGE_ACTION_RENDERERS/);
  expect(chatMessageSource).not.toMatch(/FeedbackButtons/);
  expect(messageActionRenderersSource).toMatch(/FeedbackButtons/);
  expect(chatMessageSource).toMatch(/isAuthenticated &&\s*sessionId &&/);
  expect(chatMessageSource).not.toMatch(/canUseFeedbackAction/);
});

test("shared page passes public plugin runtime state into chat messages", () => {
  const sharedPageSource = readFileSync(
    resolve(__dirname, "../SharedPage.tsx"),
    "utf8",
  );

  expect(sharedPageSource).toMatch(/useExtensionContributions/);
  expect(sharedPageSource).toMatch(/const EMPTY_RUNTIME_PLUGINS/);
  expect(sharedPageSource).toMatch(/extensionContributions\?\.plugins \?\? EMPTY_RUNTIME_PLUGINS/);
  expect(sharedPageSource).toMatch(/runtimePlugins=\{runtimePlugins\}/);
  expect(sharedPageSource).not.toMatch(/pluginRuntimeApi\.listContributions\(\)/);
  expect(sharedPageSource).not.toMatch(/setRuntimePlugins/);
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

  expect(sharedPageSource).toMatch(/resolveSharedAssistantIdentity/);
  expect(sharedPageSource).toMatch(/resolveSharedPluginAssistantIdentity/);
  expect(sharedPageSource).toMatch(/resolvePluginAssistantIdentitySnapshot/);
  expect(sharedPageSource).toMatch(/sharedAssistant/);
  expect(sharedPageSource).toMatch(/sharedPluginAssistant/);
  expect(sharedPageSource).not.toMatch(/session\.agent_id === "team"/);
  expect(assistantIdentitySource).toMatch(/buildAssistantIdentityResolverContributions/);
  expect(assistantIdentitySource).toMatch(/agent_team\.TeamAssistantIdentity/);
  expect(sharedPageSource).not.toMatch(/\{data\.session\.team_name\}/);
  expect(sharedPageSource).toMatch(/\{sharedPluginAssistant\.name\}/);
  expect(sharedPageSource).toMatch(/personaName=\{sharedAssistant\.name\}/);
  expect(sharedPageSource).toMatch(/personaAvatar=\{sharedAssistant\.avatar\}/);
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

  expect(shareApiSource).toMatch(/async update\(/);
  expect(shareApiSource).toMatch(/method: "PATCH"/);
  expect(shareDialogSource).toMatch(/editingShare/);
  expect(shareDialogSource).toMatch(/handleEditShare/);
  expect(shareDialogSource).toMatch(/handleSaveShare/);
  expect(shareDialogSource).toMatch(/share\.saveShare/);
});
