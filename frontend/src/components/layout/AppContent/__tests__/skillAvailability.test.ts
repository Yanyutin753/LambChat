import {
  buildEffectiveSkills,
  countEnabledSkills,
} from "../skillAvailability.ts";
import type { SkillResponse } from "../../../../types";

function skill(name: string, enabled = true): SkillResponse {
  return {
    name,
    description: "",
    tags: [],
    enabled,
    source: "manual",
    files: {},
    file_count: 1,
    installed_from: "manual",
    is_published: false,
    marketplace_is_active: true,
  };
}

test("limits persona skills by whitelist and then applies disabled skills", () => {
  const result = buildEffectiveSkills({
    skills: [skill("planner"), skill("writer"), skill("other")],
    skillsLoading: false,
    personaSkillNames: ["planner", "writer"],
    disabledSkillNames: ["writer"],
  });

  expect(result.map((item) => [item.name, item.enabled])).toEqual([
    ["planner", true],
    ["writer", false],
  ]);
  expect(countEnabledSkills(result)).toBe(1);
});

test("falls back to disabled-skills mode without a persona whitelist", () => {
  const result = buildEffectiveSkills({
    skills: [skill("planner"), skill("writer"), skill("globally-off", false)],
    skillsLoading: false,
    disabledSkillNames: ["writer"],
  });

  expect(result.map((item) => [item.name, item.enabled])).toEqual([
    ["planner", true],
    ["writer", false],
  ]);
  expect(countEnabledSkills(result)).toBe(1);
});
