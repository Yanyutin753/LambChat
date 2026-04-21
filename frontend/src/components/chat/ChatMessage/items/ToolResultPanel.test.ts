import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("mobile tool result panel slide-in keeps the sheet opaque", () => {
  const componentSource = readFileSync(
    new URL("./ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );
  const animationsSource = readFileSync(
    new URL("../../../../styles/animations.css", import.meta.url),
    "utf8",
  );
  const slideUpAnimation = animationsSource.match(
    /@keyframes\s+slide-up-fullscreen\s*\{(?<body>[\s\S]*?)\n\}/,
  )?.groups?.body;

  assert.ok(slideUpAnimation, "slide-up-fullscreen animation should exist");
  assert.doesNotMatch(
    slideUpAnimation,
    /\bopacity\s*:/,
    "sliding the mobile sheet should not reveal content underneath",
  );
  assert.doesNotMatch(
    componentSource,
    /transform:\s*"translateY\(100%\)"\s*,\s*opacity:\s*0/,
    "pre-animation mobile sheet state should keep its opaque background",
  );
});
