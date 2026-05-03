import type {
  PersonaPreset,
  PersonaPresetCreate,
  PersonaPresetStatus,
  PersonaPresetUpdate,
} from "../../types";

export interface PersonaPresetEditorDraft {
  name: string;
  description: string;
  avatar: string;
  system_prompt: string;
  tags: string[];
  skill_names: string[];
}

export interface PersonaPresetEditorOptions {
  scope: "user" | "global";
  status: PersonaPresetStatus;
}

export function buildPersonaPresetPayload(
  preset: null,
  draft: PersonaPresetEditorDraft,
  options: PersonaPresetEditorOptions,
): PersonaPresetCreate;
export function buildPersonaPresetPayload(
  preset: PersonaPreset,
  draft: PersonaPresetEditorDraft,
  options: PersonaPresetEditorOptions,
): PersonaPresetUpdate;
export function buildPersonaPresetPayload(
  preset: PersonaPreset | null,
  draft: PersonaPresetEditorDraft,
  options: PersonaPresetEditorOptions,
): PersonaPresetCreate | PersonaPresetUpdate {
  const base = {
    name: draft.name,
    description: draft.description,
    avatar: draft.avatar || null,
    system_prompt: draft.system_prompt,
    tags: draft.tags,
    skill_names: draft.skill_names,
  };

  if (preset) {
    if (preset.scope === "global") {
      return {
        ...base,
        visibility: "public",
        status: options.status,
      };
    }

    return base;
  }

  if (options.scope === "global") {
    return {
      ...base,
      scope: "global",
      visibility: "public",
      status: options.status,
    };
  }

  return {
    ...base,
    scope: "user",
    visibility: "private",
    status: "draft",
  };
}
