import type { PersonaPreset } from "../../types";

export interface PersonaPresetCapabilities {
  canCopy: boolean;
  canEdit: boolean;
  canDelete: boolean;
}

export function getPersonaPresetCapabilities(
  preset: PersonaPreset,
  options: {
    canWrite: boolean;
    canAdmin: boolean;
  },
): PersonaPresetCapabilities {
  if (preset.scope === "global") {
    return {
      canCopy: options.canWrite,
      canEdit: options.canAdmin,
      canDelete: options.canAdmin,
    };
  }

  return {
    canCopy: false,
    canEdit: options.canWrite,
    canDelete: options.canWrite,
  };
}
