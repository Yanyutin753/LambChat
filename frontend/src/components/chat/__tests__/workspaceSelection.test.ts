import { expect, test } from "vitest";
import {
  parseWorkspaceSelection,
  isCurrentWorkspaceMachine,
  workspaceOptionPatch,
} from "../workspaceSelection";

test("directory entry belongs to the current machine in local mode", () => {
  expect(isCurrentWorkspaceMachine("local", "m1", "m1")).toBe(true);
  expect(isCurrentWorkspaceMachine("cloud", "m1", "m1")).toBe(false);
  expect(isCurrentWorkspaceMachine("local", "m2", "m1")).toBe(false);
  expect(isCurrentWorkspaceMachine("local", "m1", null)).toBe(false);
});

test("selecting a directory updates machine and mode as one binding", () => {
  const selection = {
    id: `local-${"a".repeat(32)}`,
    machineId: "m2",
    path: "/repo",
  };
  expect(
    workspaceOptionPatch("sandbox_workspace", JSON.stringify(selection)),
  ).toEqual({
    sandbox: "local",
    sandbox_machine_id: "m2",
    sandbox_workspace: JSON.stringify(selection),
  });
  expect(workspaceOptionPatch("sandbox_machine_id", "m3")).toEqual({
    sandbox_machine_id: "m3",
    sandbox_workspace: "",
  });
  expect(workspaceOptionPatch("sandbox", "cloud")).toEqual({
    sandbox: "cloud",
    sandbox_workspace: "",
    sandbox_machine_id: "",
  });
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
