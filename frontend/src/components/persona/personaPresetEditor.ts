import type {
  PersonaPreset,
  PersonaPresetCreate,
  PersonaStarterPrompt,
  PersonaPresetStatus,
  PersonaPresetUpdate,
} from "../../types";

export interface StarterPromptDraftRow {
  icon: string;
  text: string;
}

export interface PersonaPresetEditorDraft {
  name: string;
  description: string;
  avatar: string;
  system_prompt: string;
  starter_prompts: PersonaStarterPrompt[];
  tags: string[];
  skill_names: string[];
  plugin_names: string[];
  mcp_server_names: string[];
}

export interface PersonaPresetEditorOptions {
  scope: "user" | "global";
  status: PersonaPresetStatus;
}

export function stringifyStarterPromptText(
  text: PersonaStarterPrompt["text"],
): string {
  return typeof text === "string" ? text : JSON.stringify(text);
}

export function starterPromptsToDraftRows(
  prompts: PersonaStarterPrompt[] | undefined,
): StarterPromptDraftRow[] {
  return (prompts ?? []).map((prompt) => ({
    icon: prompt.icon ?? "",
    text: stringifyStarterPromptText(prompt.text),
  }));
}

export function parseStarterPromptText(
  text: string,
): PersonaStarterPrompt["text"] {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{")) return trimmed;
  try {
    const parsed = JSON.parse(trimmed);
    if (
      parsed &&
      typeof parsed === "object" &&
      Object.values(parsed as Record<string, unknown>).every(
        (value) => typeof value === "string",
      )
    ) {
      return parsed as Record<string, string>;
    }
  } catch {
    return trimmed;
  }
  return trimmed;
}

export function draftRowsToStarterPrompts(
  rows: StarterPromptDraftRow[],
): PersonaStarterPrompt[] {
  return rows
    .map((row) => ({
      icon: row.icon.trim() || null,
      text: parseStarterPromptText(row.text),
    }))
    .filter((prompt) =>
      typeof prompt.text === "string"
        ? prompt.text.trim().length > 0
        : Object.keys(prompt.text).length > 0,
    );
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
    starter_prompts: draft.starter_prompts,
    tags: draft.tags,
    skill_names: draft.skill_names,
    plugin_names: draft.plugin_names,
    mcp_server_names: draft.mcp_server_names,
  };

  if (preset) {
    if (options.scope === "global") {
      return {
        ...base,
        ...(preset.scope !== "global" ? { scope: "global" } : {}),
        visibility: "public",
        status: options.status,
      };
    }

    if (preset.scope === "global") {
      return {
        ...base,
        scope: "user",
        visibility: "private",
        status: "draft",
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
