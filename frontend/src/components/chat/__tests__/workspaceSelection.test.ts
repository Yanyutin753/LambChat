import { expect, test } from "vitest";
import {
  parseWorkspaceSelection,
  isCurrentWorkspaceMachine,
} from "../workspaceSelection";

test("directory entry requires the current online machine and local mode", () => {
  expect(isCurrentWorkspaceMachine("local", "m1", "m1", true)).toBe(true);
  expect(isCurrentWorkspaceMachine("cloud", "m1", "m1", true)).toBe(false);
  expect(isCurrentWorkspaceMachine("local", "m2", "m1", true)).toBe(false);
  expect(isCurrentWorkspaceMachine("local", "m1", null, true)).toBe(false);
  expect(isCurrentWorkspaceMachine("local", "m1", "m1", false)).toBe(false);
});

test("saved directory round trips and malformed options are ignored", () => {
  const selection = {
    id: `local-${"a".repeat(32)}`,
    machineId: "m1",
    path: "C:\\Project",
  };
  expect(parseWorkspaceSelection(JSON.stringify(selection))).toEqual(selection);
  for (const value of [undefined, true, "null", "{}", "broken"]) {
    expect(parseWorkspaceSelection(value)).toBeNull();
  }
});
