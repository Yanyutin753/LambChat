import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("project header actions share equal slots and a single gap", () => {
  const source = readFileSync(
    new URL("../ProjectItem.tsx", import.meta.url),
    "utf8",
  );
  const actions = source.slice(
    source.indexOf("{/* Project actions */}"),
    source.indexOf("{/* Expandable content"),
  );
  expect(actions).toContain('className="flex shrink-0 items-center gap-1');
  expect(actions.match(/h-8 w-6/g)).toHaveLength(3);
  expect(actions.match(/max-sm:h-9 max-sm:w-9/g)).toHaveLength(2);
  expect(actions).toContain("max-sm:h-11 max-sm:w-11");
});

test("project actions reveal on hover or keyboard focus and reveal on touch", () => {
  const source = readFileSync(
    new URL("../ProjectItem.tsx", import.meta.url),
    "utf8",
  );
  const actions = source.slice(
    source.indexOf("{/* Project actions */}"),
    source.indexOf("{/* Expandable content"),
  );
  expect(actions).toContain("sidebar-action-reveal");
  expect(actions).toContain("<ProjectWorkspaceDetails");
});

test("projects use a closed folder when collapsed and an open folder when expanded", () => {
  const source = readFileSync(
    new URL("../ProjectItem.tsx", import.meta.url),
    "utf8",
  );
  expect(source).toContain("<FolderClosed");
  expect(source).toContain("<FolderOpen");
  expect(source).not.toContain("<DynamicIcon");
  expect(source).not.toContain("handleStartIconEdit");
});
