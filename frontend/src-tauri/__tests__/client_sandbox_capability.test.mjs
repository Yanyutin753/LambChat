import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const capability = JSON.parse(
  readFileSync(
    new URL("../capabilities/default.json", import.meta.url),
    "utf8",
  ),
);
const permissions = readFileSync(
  new URL("../permissions/client-sandbox.toml", import.meta.url),
  "utf8",
);

test("default desktop capability allows client sandbox commands", () => {
  for (const permission of [
    "allow-client-sandbox-execute",
    "allow-client-sandbox-read-file",
    "allow-client-sandbox-write-file",
    "allow-client-sandbox-list",
  ]) {
    assert.ok(
      capability.permissions.includes(permission),
      `missing ${permission}`,
    );
  }
});

test("client sandbox permissions map to tauri commands", () => {
  for (const command of [
    "client_sandbox_execute",
    "client_sandbox_read_file",
    "client_sandbox_write_file",
    "client_sandbox_list",
  ]) {
    assert.match(
      permissions,
      new RegExp(`commands\\.allow = \\["${command}"\\]`),
    );
  }
});
