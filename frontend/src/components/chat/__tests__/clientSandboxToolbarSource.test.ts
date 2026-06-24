import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const toolbarSource = readFileSync(
  new URL("../ClientSandboxButton.tsx", import.meta.url),
  "utf8",
);
const chatInputTypesSource = readFileSync(
  new URL("../chatInputTypes.ts", import.meta.url),
  "utf8",
);
const chatInputSource = readFileSync(
  new URL("../ChatInput.tsx", import.meta.url),
  "utf8",
);
const chatViewSource = readFileSync(
  new URL("../../layout/AppContent/ChatView.tsx", import.meta.url),
  "utf8",
);

test("chat toolbar can enable the current Tauri desktop as the user sandbox", () => {
  assert.doesNotMatch(toolbarSource, /bindClientSandboxSession/);
  assert.match(toolbarSource, /getOrCreateClientSandboxDeviceId/);
  assert.match(toolbarSource, /getClientSandboxWorkspaceRoot/);
  assert.match(toolbarSource, /shouldStartClientSandboxService/);
  assert.match(toolbarSource, /startClientSandboxService/);
  assert.match(toolbarSource, /enableClientSandboxPreference/);
  assert.match(toolbarSource, /chat\.clientSandbox\.enabled/);
  assert.match(toolbarSource, /Monitor/);
  assert.match(toolbarSource, /toast\.success/);
});

test("client sandbox button does not require a session before enabling", () => {
  assert.doesNotMatch(toolbarSource, /disabled = !sessionId \|\| isBinding/);
  assert.doesNotMatch(toolbarSource, /if \(!sessionId\)/);
  assert.doesNotMatch(toolbarSource, /bindClientSandboxSession/);
  assert.match(toolbarSource, /chat\.clientSandbox\.enable/);
});

test("chat input carries session id to the local sandbox toolbar action", () => {
  assert.match(chatInputTypesSource, /sessionId\?: string \| null/);
  assert.match(chatInputSource, /sessionId,/);
  assert.match(
    chatInputSource,
    /<ClientSandboxButton[\s\S]*sessionId=\{sessionId\}/,
  );
  assert.match(chatViewSource, /sessionId,/);
  assert.match(chatViewSource, /chatInputProps = \{[\s\S]*sessionId,/);
});
