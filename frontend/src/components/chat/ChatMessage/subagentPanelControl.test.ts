import assert from "node:assert/strict";
import test from "node:test";
import { shouldAutoOpenSubagentPanel } from "./subagentPanelControl.ts";

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
