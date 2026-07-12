import { resolvePersonaEnabledSkills } from "../personaRequestConfig.ts";

test("does not send an enabled skills whitelist when no persona is selected", () => {
  expect(resolvePersonaEnabledSkills(null, ["planning"])).toBe(undefined);
  expect(resolvePersonaEnabledSkills(undefined, [])).toBe(undefined);
});

test("sends the persona skills whitelist when a persona is selected", () => {
  expect(resolvePersonaEnabledSkills("preset-1", ["planning"])).toEqual([
    "planning",
  ]);
});

test("falls back to global skills when selected persona has no configured skills", () => {
  expect(resolvePersonaEnabledSkills("preset-1", [])).toBe(undefined);
  expect(resolvePersonaEnabledSkills("preset-1", undefined)).toBe(undefined);
});
