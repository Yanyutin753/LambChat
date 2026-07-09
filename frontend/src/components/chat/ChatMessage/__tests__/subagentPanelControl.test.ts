import {
  dismissSubagentPanelAutoOpen,
  isSubagentPanelAutoOpenDismissed,
  resetSubagentPanelAutoOpenDismissal,
  shouldAutoOpenSubagentPanel,
  shouldExpandSubagentProcessByDefault,
} from "../subagentPanelControl.ts";

test("auto-opens a running subagent only when no panel is already open", () => {
  expect(
    shouldAutoOpenSubagentPanel({
      status: "running",
      anyPanelOpen: false,
    }),
  ).toBe(true);

  expect(
    shouldAutoOpenSubagentPanel({
      status: "running",
      anyPanelOpen: true,
    }),
  ).toBe(false);
});

test("does not auto-open completed or failed subagents", () => {
  expect(
    shouldAutoOpenSubagentPanel({
      status: "complete",
      anyPanelOpen: false,
    }),
  ).toBe(false);

  expect(
    shouldAutoOpenSubagentPanel({
      status: "error",
      anyPanelOpen: false,
    }),
  ).toBe(false);
});

test("does not auto-open after the user dismisses an auto-opened subagent panel", () => {
  expect(
    shouldAutoOpenSubagentPanel({
      status: "running",
      anyPanelOpen: false,
      autoOpenDismissed: true,
    }),
  ).toBe(false);
});

test("tracks whether subagent panel auto-open has been dismissed", () => {
  resetSubagentPanelAutoOpenDismissal();
  expect(isSubagentPanelAutoOpenDismissed()).toBe(false);

  dismissSubagentPanelAutoOpen();

  expect(isSubagentPanelAutoOpenDismissed()).toBe(true);

  resetSubagentPanelAutoOpenDismissal();
  expect(isSubagentPanelAutoOpenDismissed()).toBe(false);
});

test("expands the subagent process section by default while running", () => {
  expect(shouldExpandSubagentProcessByDefault("running")).toBe(true);
  expect(shouldExpandSubagentProcessByDefault("pending")).toBe(false);
  expect(shouldExpandSubagentProcessByDefault("complete")).toBe(false);
  expect(shouldExpandSubagentProcessByDefault("error")).toBe(false);
  expect(shouldExpandSubagentProcessByDefault("cancelled")).toBe(false);
  expect(shouldExpandSubagentProcessByDefault(undefined)).toBe(false);
});
