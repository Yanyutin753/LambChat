import { resolveSkillsHubTab } from "../state.ts";

test("keeps the requested tab when both permissions are available", () => {
  expect(resolveSkillsHubTab(undefined, true, true)).toBe("skills");
  expect(resolveSkillsHubTab("skills", true, true)).toBe("skills");
  expect(resolveSkillsHubTab("marketplace", true, true)).toBe("marketplace");
});

test("resolves to local skills when only local skills are available", () => {
  expect(resolveSkillsHubTab(undefined, true, false)).toBe("skills");
  expect(resolveSkillsHubTab("skills", true, false)).toBe("skills");
});

test("resolves to marketplace when only marketplace is available", () => {
  expect(resolveSkillsHubTab(undefined, false, true)).toBe("marketplace");
  expect(resolveSkillsHubTab("marketplace", false, true)).toBe("marketplace");
});

test("falls back to the accessible tab when the requested tab is inaccessible", () => {
  expect(resolveSkillsHubTab("marketplace", true, false)).toBe("skills");
  expect(resolveSkillsHubTab("skills", false, true)).toBe("marketplace");
});

test("returns null when neither tab is accessible", () => {
  expect(resolveSkillsHubTab(undefined, false, false)).toBe(null);
  expect(resolveSkillsHubTab("skills", false, false)).toBe(null);
  expect(resolveSkillsHubTab("marketplace", false, false)).toBe(null);
});
