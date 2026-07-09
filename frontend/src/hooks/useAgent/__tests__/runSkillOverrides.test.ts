import { resolveRunEnabledSkills } from "../runSkillOverrides.ts";

test("uses a per-run skills whitelist before persona skills", () => {
  expect(
    resolveRunEnabledSkills({
      personaPresetId: "preset-1",
      personaEnabledSkills: ["persona-skill"],
      runEnabledSkills: ["selected-skill"],
    }),
  ).toEqual(["selected-skill"]);
});

test("falls back to persona skills when there is no per-run whitelist", () => {
  expect(
    resolveRunEnabledSkills({
      personaPresetId: "preset-1",
      personaEnabledSkills: ["persona-skill"],
    }),
  ).toEqual(["persona-skill"]);
});

test("keeps an empty per-run whitelist as no skills for this run", () => {
  expect(
    resolveRunEnabledSkills({
      personaPresetId: "preset-1",
      personaEnabledSkills: ["persona-skill"],
      runEnabledSkills: [],
    }),
  ).toEqual([]);
});
