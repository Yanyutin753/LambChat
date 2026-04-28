import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("chat view places the assistant banner above both chat input entry points", () => {
  const chatViewSource = readFileSync(
    new URL("./ChatView.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    chatViewSource,
    /chatInputHeader=\{assistantBanner\}/,
    "ChatView should pass the assistant banner into the WelcomePage input area",
  );
  assert.match(
    chatViewSource,
    /\{messages\.length > 0 && assistantBanner\}\s*\{messages\.length > 0 && <ChatInput/,
    "ChatView should render the assistant banner above the bottom ChatInput",
  );
});
