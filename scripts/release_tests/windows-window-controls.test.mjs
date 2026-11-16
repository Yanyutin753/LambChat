import test from "node:test";
import assert from "node:assert/strict";
import { exerciseMaximizeRestore } from "./windows-window-controls.mjs";

for (const initiallyMaximized of [false, true]) {
  test(`maximize/restore from initial maximized=${initiallyMaximized}`, async () => {
    let maximized = initiallyMaximized;
    const clicks = [];
    const controls = {
      getByRole(role, { name }) {
        assert.equal(role, "button");
        return {
          async waitFor() {
            assert.equal(name, maximized ? "还原" : "最大化");
          },
          async click() {
            assert.equal(name, maximized ? "还原" : "最大化");
            clicks.push(name);
            maximized = !maximized;
          },
        };
      },
    };
    const page = {
      async evaluate(fn) {
        globalThis.window = { __TAURI_INTERNALS__: {
          metadata: { currentWindow: { label: "main" } },
          async invoke(command, args) {
            assert.deepEqual(args, { label: "main" });
            assert.equal(command, "plugin:window|is_maximized");
            return maximized;
          },
        } };
        try { return await fn(); } finally { delete globalThis.window; }
      },
    };
    await exerciseMaximizeRestore(page, controls);
    assert.equal(maximized, false);
    assert.deepEqual(clicks, initiallyMaximized
      ? ["还原", "最大化", "还原"] : ["最大化", "还原"]);
  });
}
