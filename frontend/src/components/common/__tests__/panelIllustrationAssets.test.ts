import { existsSync } from "node:fs";
import { expect, test } from "vitest";

const panels = [
  "persona",
  "skills",
  "marketplace",
  "files",
  "bookmarks",
  "team",
  "memory",
  "notifications",
  "feedback",
  "feedback-positive",
  "schedule",
  "usage",
  "mcp",
  "users",
  "roles",
  "agents",
  "models",
  "settings",
  "channels",
];

test.each(panels)("%s has its own bundled panel avatar", (panel) => {
  expect(
    existsSync(`public/images/illustrations/lamb-panel-${panel}.png`),
  ).toBe(true);
});
