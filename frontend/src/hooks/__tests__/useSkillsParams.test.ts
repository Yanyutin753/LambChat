import {
  DEFAULT_SKILL_LIST_LIMIT,
  resolveSkillListParams,
  resolveSkillListState,
} from "../useSkills.ts";

test("resolveSkillListParams requests one page by default", () => {
  expect(resolveSkillListParams(undefined, undefined)).toEqual({
    limit: 20,
  });
});

test("resolveSkillListParams gives explicit fetch params priority", () => {
  expect(
    resolveSkillListParams({ skip: 20, limit: 20 }, { limit: 50 }),
  ).toEqual({ skip: 20, limit: 20 });
});

test("resolveSkillListState replaces skills in normal paged mode", () => {
  const result = resolveSkillListState({
    currentSkills: [{ name: "first", enabled: true }],
    incomingSkills: [{ name: "second", enabled: true }],
    params: { skip: DEFAULT_SKILL_LIST_LIMIT, limit: DEFAULT_SKILL_LIST_LIMIT },
    appendPages: false,
  });

  expect(result.map((skill) => skill.name)).toEqual(["second"]);
});

test("resolveSkillListState appends later pages without duplicating skills", () => {
  const result = resolveSkillListState({
    currentSkills: [
      { name: "alpha", enabled: true },
      { name: "bravo", enabled: true },
    ],
    incomingSkills: [
      { name: "bravo", enabled: false },
      { name: "charlie", enabled: true },
    ],
    params: { skip: DEFAULT_SKILL_LIST_LIMIT, limit: DEFAULT_SKILL_LIST_LIMIT },
    appendPages: true,
  });

  expect(result.map((skill) => [skill.name, skill.enabled])).toEqual([
    ["alpha", true],
    ["bravo", false],
    ["charlie", true],
  ]);
});
