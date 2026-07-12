import { updateRunSkillNamesForSlashSelection } from "../runSkillSelection.ts";

test("slash-selecting a skill starts a next-message whitelist with that skill", () => {
  expect(
    updateRunSkillNamesForSlashSelection({
      currentRunSkillNames: null,
      availableSkillNames: ["writer"],
      selectedSkillName: "writer",
    }),
  ).toEqual(["writer"]);
});

test("slash-selecting additional skills toggles within the explicit next-message whitelist", () => {
  expect(
    updateRunSkillNamesForSlashSelection({
      currentRunSkillNames: ["writer"],
      availableSkillNames: ["writer", "research"],
      selectedSkillName: "research",
    }),
  ).toEqual(["writer", "research"]);

  expect(
    updateRunSkillNamesForSlashSelection({
      currentRunSkillNames: ["writer", "research"],
      availableSkillNames: ["writer", "research"],
      selectedSkillName: "writer",
    }),
  ).toEqual(["research"]);
});
