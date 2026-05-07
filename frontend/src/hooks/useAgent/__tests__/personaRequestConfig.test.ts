import test from "node:test";
import assert from "node:assert/strict";

import { resolvePersonaEnabledSkills } from "../personaRequestConfig.ts";

test("does not send an enabled skills whitelist when no persona is selected", () => {
  assert.equal(resolvePersonaEnabledSkills(null, ["planning"]), undefined);
  assert.equal(resolvePersonaEnabledSkills(undefined, []), undefined);
});

test("sends the persona skills whitelist when a persona is selected", () => {
  assert.deepEqual(resolvePersonaEnabledSkills("preset-1", ["planning"]), [
    "planning",
  ]);
});

test("falls back to global skills when selected persona has no configured skills", () => {
  assert.equal(resolvePersonaEnabledSkills("preset-1", []), undefined);
  assert.equal(resolvePersonaEnabledSkills("preset-1", undefined), undefined);
});
