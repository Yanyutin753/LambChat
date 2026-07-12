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

  expect(model.description).toBe("Plan before acting.");
  expect(model.primaryTag).toBe("planning");
  expect(model.secondaryTags).toEqual(["writing", "analysis", "review"]);
  expect(model.hiddenTagCount).toBe(1);
  expect(model.canCopy).toBe(false);
  expect(model.canEdit).toBe(true);
  expect(model.canDelete).toBe(true);
  expect(model.showUseAction).toBe(true);
  expect(model.showClearAction).toBe(false);
  expect(model.skillCount).toBe(2);
  expect(model.tagCount).toBe(5);
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

  expect(model.description).toBe("Official helper");
  expect(model.canCopy).toBe(true);
  expect(model.canEdit).toBe(false);
  expect(model.canDelete).toBe(false);
  expect(model.showUseAction).toBe(false);
  expect(model.showClearAction).toBe(true);
  expect(model.skillCount).toBe(0);
});

test("getPersonaFormCopy returns create and edit copy", () => {
  expect(getPersonaFormCopy(false)).toEqual({
    titleKey: "personaPresets.createMine",
    titleFallback: "新建我的角色",
    subtitleKey: "personaPresets.createHint",
    subtitleFallback: "定义角色的行为、语气和能力边界",
  });

  expect(getPersonaFormCopy(true)).toEqual({
    titleKey: "personaPresets.editMine",
    titleFallback: "编辑我的角色",
    subtitleKey: "personaPresets.editHint",
    subtitleFallback: "修改角色的名称、提示词和标签",
  });
});
