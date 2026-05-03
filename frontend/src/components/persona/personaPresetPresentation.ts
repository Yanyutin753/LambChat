import { getPersonaPresetCapabilities } from "./personaPresetAccess";
import type { PersonaPreset } from "../../types";

export interface PersonaCardModel {
  description: string;
  primaryTag?: string;
  secondaryTags: string[];
  hiddenTagCount: number;
  canCopy: boolean;
  canEdit: boolean;
  canDelete: boolean;
  showUseAction: boolean;
  showClearAction: boolean;
  skillCount: number;
  tagCount: number;
}

export function buildPersonaCardModel(
  preset: PersonaPreset,
  options: {
    canWrite: boolean;
    canAdmin?: boolean;
    isSelected: boolean;
  },
): PersonaCardModel {
  const capabilities = getPersonaPresetCapabilities(preset, {
    canWrite: options.canWrite,
    canAdmin: options.canAdmin ?? false,
  });

  return {
    description: preset.description || preset.system_prompt,
    primaryTag: preset.tags[0],
    secondaryTags: preset.tags.slice(1, 4),
    hiddenTagCount: Math.max(preset.tags.length - 4, 0),
    canCopy: capabilities.canCopy,
    canEdit: capabilities.canEdit,
    canDelete: capabilities.canDelete,
    showUseAction: !options.isSelected,
    showClearAction: options.isSelected,
    skillCount: preset.skill_names.length,
    tagCount: preset.tags.length,
  };
}

export function getPersonaFormCopy(isEditing: boolean) {
  if (isEditing) {
    return {
      titleKey: "personaPresets.editMine",
      titleFallback: "编辑我的角色",
      subtitleKey: "personaPresets.editHint",
      subtitleFallback: "修改角色的名称、提示词和标签",
    };
  }

  return {
    titleKey: "personaPresets.createMine",
    titleFallback: "新建我的角色",
    subtitleKey: "personaPresets.createHint",
    subtitleFallback: "定义角色的行为、语气和能力边界",
  };
}
