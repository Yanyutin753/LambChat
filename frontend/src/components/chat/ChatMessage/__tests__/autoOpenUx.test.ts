import { expect, test } from "vitest";

import {
  getStreamFollowSignal,
  isUserReadingHistory,
  resetStreamFollowSignal,
  setStreamFollowSignal,
} from "../../streamFollowSignal";
import {
  clearSubagentPanelAutoOpenState,
  dismissSubagentPanelAutoOpen,
  isSubagentPanelAutoOpenDismissed,
  shouldAutoOpenSubagentPanel,
} from "../subagentPanelControl";

test("reading-history signal derives from detach and bottom state", () => {
  resetStreamFollowSignal();
  expect(isUserReadingHistory()).toBe(false);

  setStreamFollowSignal({ detached: true, nearBottom: false });
  expect(isUserReadingHistory()).toBe(true);

  setStreamFollowSignal({ detached: false });
  expect(isUserReadingHistory()).toBe(true);

  setStreamFollowSignal({ nearBottom: true });
  expect(isUserReadingHistory()).toBe(false);
  expect(getStreamFollowSignal()).toEqual({
    detached: false,
    nearBottom: true,
  });

  resetStreamFollowSignal();
});

test("subagent auto-open is suppressed while the user reads history", () => {
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
      alreadyAutoOpened: false,
      autoOpenDismissed: false,
      userReadingHistory: true,
    }),
  ).toBe(false);
});

test("subagent auto-open marks do not survive session switches", () => {
  dismissSubagentPanelAutoOpen("subagent-test-agent");
  expect(isSubagentPanelAutoOpenDismissed("subagent-test-agent")).toBe(true);

  clearSubagentPanelAutoOpenState();
  expect(isSubagentPanelAutoOpenDismissed("subagent-test-agent")).toBe(false);
});
