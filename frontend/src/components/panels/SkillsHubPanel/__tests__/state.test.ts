import test from "node:test";
import assert from "node:assert/strict";

import { resolveSkillsHubTab } from "../state.ts";

test("keeps the requested tab when both permissions are available", () => {
  assert.equal(resolveSkillsHubTab(undefined, true, true), "skills");
  assert.equal(resolveSkillsHubTab("skills", true, true), "skills");
  assert.equal(resolveSkillsHubTab("marketplace", true, true), "marketplace");
  assert.equal(resolveSkillsHubTab("plugins", true, true), "plugins");
});

test("resolves to local skills when only local skills are available", () => {
  assert.equal(resolveSkillsHubTab(undefined, true, false), "skills");
  assert.equal(resolveSkillsHubTab("skills", true, false), "skills");
});

test("resolves to marketplace when only marketplace is available", () => {
  assert.equal(resolveSkillsHubTab(undefined, false, true), "marketplace");
  assert.equal(resolveSkillsHubTab("marketplace", false, true), "marketplace");
  assert.equal(resolveSkillsHubTab("plugins", false, true), "plugins");
});

test("falls back to the accessible tab when the requested tab is inaccessible", () => {
  assert.equal(resolveSkillsHubTab("marketplace", true, false), "skills");
  assert.equal(resolveSkillsHubTab("skills", false, true), "marketplace");
  assert.equal(resolveSkillsHubTab("plugins", true, false), "skills");
});

test("returns null when neither tab is accessible", () => {
  assert.equal(resolveSkillsHubTab(undefined, false, false), null);
  assert.equal(resolveSkillsHubTab("skills", false, false), null);
  assert.equal(resolveSkillsHubTab("marketplace", false, false), null);
  assert.equal(resolveSkillsHubTab("plugins", false, false), null);
});
