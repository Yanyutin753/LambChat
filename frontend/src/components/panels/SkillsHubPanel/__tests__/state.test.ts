import { resolveSkillsHubTab } from "../state.ts";

test("keeps the requested tab when both permissions are available", () => {
  expect(resolveSkillsHubTab(undefined, true, true)).toBe("skills");
  expect(resolveSkillsHubTab("skills", true, true)).toBe("skills");
  expect(resolveSkillsHubTab("plugins", true, true)).toBe("plugins");
});

test("resolves to local skills when only local skills are available", () => {
  expect(resolveSkillsHubTab(undefined, true, false)).toBe("skills");
  expect(resolveSkillsHubTab("skills", true, false)).toBe("skills");
});

test("resolves to plugins when only plugins are available", () => {
  expect(resolveSkillsHubTab(undefined, false, true)).toBe("plugins");
  expect(resolveSkillsHubTab("plugins", false, true)).toBe("plugins");
});

test("falls back to the accessible tab when the requested tab is inaccessible", () => {
  expect(resolveSkillsHubTab("plugins", true, false)).toBe("skills");
  expect(resolveSkillsHubTab("skills", false, true)).toBe("plugins");
});

test("returns null when neither tab is accessible", () => {
  expect(resolveSkillsHubTab(undefined, false, false)).toBe(null);
  expect(resolveSkillsHubTab("skills", false, false)).toBe(null);
  expect(resolveSkillsHubTab("plugins", false, false)).toBe(null);
});
