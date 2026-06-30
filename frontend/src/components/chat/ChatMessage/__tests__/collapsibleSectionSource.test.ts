import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("collapsible section header does not nest action buttons inside the toggle", () => {
  const componentSource = readFileSync(
    new URL("../SubagentBlocks.tsx", import.meta.url),
    "utf8",
  );
  const componentsCss = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(
    componentSource,
    /<button[\s\S]*?\{action && <span onClick=\{\(e\) => e\.stopPropagation\(\)\}>\{action\}<\/span>\}[\s\S]*?<\/button>/,
    "action controls such as CopyButton should not render inside the header toggle button",
  );
  assert.match(
    componentSource,
    /<button[\s\S]*?aria-expanded=\{expanded\}[\s\S]*?onClick=\{toggleExpanded\}/,
    "the collapsible header toggle should remain a keyboard-reachable native button",
  );
  assert.match(
    componentSource,
    /\{action && <div className="shrink-0">\{action\}<\/div>\}/,
    "action controls should render as siblings of the header toggle",
  );
  assert.match(
    componentSource,
    /"collapsible-section-card--default bg-theme-bg-card border border-theme-border shadow-sm"/,
    "default collapsible sections should render as bordered card surfaces instead of blending into the light page background",
  );
  assert.doesNotMatch(
    componentSource,
    /:\s*"bg-theme-bg-subtle"/,
    "default collapsible sections should not rely on the subtle background alone",
  );
  assert.match(
    componentsCss,
    /\.collapsible-section-card--default\s*\{[\s\S]*?background:\s*var\(--theme-bg-card\);[\s\S]*?box-shadow:/,
    "default collapsible sections should have dedicated light-mode card separation",
  );
});
