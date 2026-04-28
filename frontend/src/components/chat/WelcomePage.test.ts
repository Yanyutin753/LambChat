import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("welcome page renders an optional header above the chat input", () => {
  const welcomePageSource = readFileSync(
    new URL("./WelcomePage.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    welcomePageSource,
    /chatInputHeader\?: React\.ReactNode;/,
    "WelcomePage should accept a chatInputHeader prop",
  );
  assert.match(
    welcomePageSource,
    /\{chatInputHeader\}\s*<ChatInput/,
    "WelcomePage should render chatInputHeader immediately above ChatInput",
  );
});
