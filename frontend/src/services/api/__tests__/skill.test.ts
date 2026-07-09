import { buildSkillListUrl } from "../skill.ts";

test("buildSkillListUrl includes pagination and search params", () => {
  expect(
    buildSkillListUrl({ skip: 20, limit: 10, q: "planner", tags: ["coding"] }),
  ).toBe("/api/skills/?skip=20&limit=10&q=planner&tags=coding");
});
