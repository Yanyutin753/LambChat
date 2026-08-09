import { expect, test } from "vitest";

import {
  dismissSubagentPanelAutoOpen,
  hasSubagentPanelAutoOpened,
  isSubagentPanelAutoOpenDismissed,
  markSubagentPanelAutoOpened,
  resetSubagentPanelAutoOpenState,
  shouldAutoOpenSubagentPanel,
  shouldExpandSubagentProcessByDefault,
} from "../subagentPanelControl.ts";

test("tracks automatic opening and dismissal per subagent panel key", () => {
  resetSubagentPanelAutoOpenState("subagent:a");
  resetSubagentPanelAutoOpenState("subagent:b");
  markSubagentPanelAutoOpened("subagent:a");
  dismissSubagentPanelAutoOpen("subagent:a");

  expect(hasSubagentPanelAutoOpened("subagent:a")).toBe(true);
  expect(isSubagentPanelAutoOpenDismissed("subagent:a")).toBe(true);
  expect(hasSubagentPanelAutoOpened("subagent:b")).toBe(false);
  expect(isSubagentPanelAutoOpenDismissed("subagent:b")).toBe(false);
});

test("allows a running subagent only once while the lane is empty", () => {
  expect(
    shouldAutoOpenSubagentPanel({
      status: "running",
      laneOccupied: false,
      alreadyAutoOpened: false,
      autoOpenDismissed: false,
    }),
  ).toBe(true);
  expect(
    shouldAutoOpenSubagentPanel({
      status: "running",
      laneOccupied: false,
      alreadyAutoOpened: true,
      autoOpenDismissed: false,
    }),
  ).toBe(false);
  expect(
    shouldAutoOpenSubagentPanel({
      status: "running",
      laneOccupied: true,
      alreadyAutoOpened: false,
      autoOpenDismissed: false,
    }),
  ).toBe(false);
  expect(
    shouldAutoOpenSubagentPanel({
      status: "complete",
      laneOccupied: false,
      alreadyAutoOpened: false,
      autoOpenDismissed: false,
    }),
  ).toBe(false);
});

test("expands the subagent process section by default while running", () => {
  expect(shouldExpandSubagentProcessByDefault("running")).toBe(true);
  expect(shouldExpandSubagentProcessByDefault("pending")).toBe(false);
  expect(shouldExpandSubagentProcessByDefault("complete")).toBe(false);
  expect(shouldExpandSubagentProcessByDefault("error")).toBe(false);
  expect(shouldExpandSubagentProcessByDefault("cancelled")).toBe(false);
  expect(shouldExpandSubagentProcessByDefault(undefined)).toBe(false);
});
