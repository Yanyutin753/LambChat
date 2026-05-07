import test from "node:test";
import assert from "node:assert/strict";

import {
  buildPersonaCardModel,
  getPersonaFormCopy,
} from "../personaPresetPresentation.ts";
import type { PersonaPreset } from "../../../types";

function createPreset(overrides: Partial<PersonaPreset> = {}): PersonaPreset {
  return {
    id: "preset-1",
    scope: "user",
    name: "Planner",
    description: "",
    avatar: null,
    tags: ["planning", "writing", "analysis", "review", "extra"],
    system_prompt: "Plan before acting.",
    skill_names: ["planner", "writer"],
    visibility: "private",
    status: "draft",
    source_preset_id: null,
    copied_from_version: null,
    version: 3,
    usage_count: 12,
    created_by: null,
    updated_by: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    ...overrides,
  };
}

test("buildPersonaCardModel maps user presets to editable marketplace-style cards", () => {
  const model = buildPersonaCardModel(createPreset(), {
    canWrite: true,
    isSelected: false,
  });

  assert.equal(model.description, "Plan before acting.");
  assert.equal(model.primaryTag, "planning");
  assert.deepEqual(model.secondaryTags, ["writing", "analysis", "review"]);
  assert.equal(model.hiddenTagCount, 1);
  assert.equal(model.canCopy, false);
  assert.equal(model.canEdit, true);
  assert.equal(model.canDelete, true);
  assert.equal(model.showUseAction, true);
  assert.equal(model.showClearAction, false);
  assert.equal(model.skillCount, 2);
  assert.equal(model.tagCount, 5);
});

test("buildPersonaCardModel maps official selected presets to copyable cards", () => {
  const model = buildPersonaCardModel(
    createPreset({
      scope: "global",
      description: "Official helper",
      visibility: "public",
      status: "published",
      skill_names: [],
    }),
    {
      canWrite: true,
      isSelected: true,
    },
  );

  assert.equal(model.description, "Official helper");
  assert.equal(model.canCopy, true);
  assert.equal(model.canEdit, false);
  assert.equal(model.canDelete, false);
  assert.equal(model.showUseAction, false);
  assert.equal(model.showClearAction, true);
  assert.equal(model.skillCount, 0);
});

test("getPersonaFormCopy returns create and edit copy", () => {
  assert.deepEqual(getPersonaFormCopy(false), {
    titleKey: "personaPresets.createMine",
    titleFallback: "新建我的角色",
    subtitleKey: "personaPresets.createHint",
    subtitleFallback: "定义角色的行为、语气和能力边界",
  });

  assert.deepEqual(getPersonaFormCopy(true), {
    titleKey: "personaPresets.editMine",
    titleFallback: "编辑我的角色",
    subtitleKey: "personaPresets.editHint",
    subtitleFallback: "修改角色的名称、提示词和标签",
  });
});
