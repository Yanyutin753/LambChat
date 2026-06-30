import assert from "node:assert/strict";
import test from "node:test";
import {
  dismissSubagentPanelAutoOpen,
  isSubagentPanelAutoOpenDismissed,
  resetSubagentPanelAutoOpenDismissal,
  shouldAutoOpenSubagentPanel,
  shouldExpandSubagentProcessByDefault,
} from "../subagentPanelControl.ts";

test("auto-opens a running subagent only when no panel is already open", () => {
  assert.equal(
    shouldAutoOpenSubagentPanel({
      status: "running",
      anyPanelOpen: false,
    }),
    true,
  );

  assert.equal(
    shouldAutoOpenSubagentPanel({
      status: "running",
      anyPanelOpen: true,
    }),
    false,
  );
});

test("does not auto-open completed or failed subagents", () => {
  assert.equal(
    shouldAutoOpenSubagentPanel({
      status: "complete",
      anyPanelOpen: false,
    }),
    false,
  );

  assert.equal(
    shouldAutoOpenSubagentPanel({
      status: "error",
      anyPanelOpen: false,
    }),
    false,
  );
});

test("does not auto-open after the user dismisses an auto-opened subagent panel", () => {
  assert.equal(
    shouldAutoOpenSubagentPanel({
      status: "running",
      anyPanelOpen: false,
      autoOpenDismissed: true,
    }),
    false,
  );
});

test("tracks whether subagent panel auto-open has been dismissed", () => {
  resetSubagentPanelAutoOpenDismissal();
  assert.equal(isSubagentPanelAutoOpenDismissed(), false);

  dismissSubagentPanelAutoOpen();

  assert.equal(isSubagentPanelAutoOpenDismissed(), true);

  resetSubagentPanelAutoOpenDismissal();
  assert.equal(isSubagentPanelAutoOpenDismissed(), false);
});

test("expands the subagent process section by default while running", () => {
  assert.equal(shouldExpandSubagentProcessByDefault("running"), true);
  assert.equal(shouldExpandSubagentProcessByDefault("pending"), false);
  assert.equal(shouldExpandSubagentProcessByDefault("complete"), false);
  assert.equal(shouldExpandSubagentProcessByDefault("error"), false);
  assert.equal(shouldExpandSubagentProcessByDefault("cancelled"), false);
  assert.equal(shouldExpandSubagentProcessByDefault(undefined), false);
});
