import test from "node:test";
import assert from "node:assert/strict";

import { updateRunSkillNamesForSlashSelection } from "../runSkillSelection.ts";

test("slash-selecting a skill starts a next-message whitelist with that skill", () => {
  assert.deepEqual(
    updateRunSkillNamesForSlashSelection({
      currentRunSkillNames: null,
      availableSkillNames: ["writer"],
      selectedSkillName: "writer",
    }),
    ["writer"],
  );
});

test("slash-selecting additional skills toggles within the explicit next-message whitelist", () => {
  assert.deepEqual(
    updateRunSkillNamesForSlashSelection({
      currentRunSkillNames: ["writer"],
      availableSkillNames: ["writer", "research"],
      selectedSkillName: "research",
    }),
    ["writer", "research"],
  );

  assert.deepEqual(
    updateRunSkillNamesForSlashSelection({
      currentRunSkillNames: ["writer", "research"],
      availableSkillNames: ["writer", "research"],
      selectedSkillName: "writer",
    }),
    ["research"],
  );
});
