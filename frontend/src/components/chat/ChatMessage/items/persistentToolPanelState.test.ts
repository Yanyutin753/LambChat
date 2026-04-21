import assert from "node:assert/strict";
import test from "node:test";
import {
  closePersistentToolPanel,
  getPersistentToolPanelState,
  openPersistentToolPanel,
  updatePersistentToolPanel,
} from "./persistentToolPanelState.tsx";

test("keyed panel updates do not replace another open panel", () => {
  closePersistentToolPanel();
  openPersistentToolPanel({
    title: "Tool result",
    status: "success",
    children: "tool body",
    panelKey: "tool:1",
  });

  updatePersistentToolPanel(
    (prev) => ({
      ...prev,
      title: "Summary",
      children: "summary body",
    }),
    "summary:1",
  );

  assert.equal(getPersistentToolPanelState()?.title, "Tool result");
  assert.equal(getPersistentToolPanelState()?.children, "tool body");

  closePersistentToolPanel();
});
