import assert from "node:assert/strict";
import test from "node:test";
import {
  isTauriDesktopRuntime,
  shouldStartClientSandboxService,
} from "../device";

test("detects tauri desktop by bridge globals", () => {
  assert.equal(isTauriDesktopRuntime({ __TAURI_INTERNALS__: {} }), true);
  assert.equal(isTauriDesktopRuntime({ isTauri: true }), true);
});

test("detects tauri desktop by webview origin", () => {
  assert.equal(
    isTauriDesktopRuntime(null, {
      protocol: "http:",
      hostname: "tauri.localhost",
    }),
    true,
  );
  assert.equal(isTauriDesktopRuntime(null, { protocol: "tauri:" }), true);
});

test("starts the client sandbox service in tauri webview origins", () => {
  assert.equal(
    shouldStartClientSandboxService(
      { protocol: "http:", hostname: "tauri.localhost" },
      null,
    ),
    true,
  );
});
