import type {
  PersonaPreset,
  PersonaPresetCreate,
  PersonaPresetStatus,
  PersonaPresetUpdate,
} from "../../types";

export type {
  PersonaPreset,
  PersonaPresetCreate,
  PersonaPresetStatus,
  PersonaPresetUpdate,
};

export interface PersonaEditorDraft {
  name: string;
  description: string;
  avatar: string;
  system_prompt: string;
  starter_prompts: { icon: string; text: string }[];
  tags: string;
  skill_names: string[];
  plugin_names: string[];
  mcp_server_names: string[];
}

export interface PersonaEditorModalProps {
  showModal: boolean;
  editingPreset: PersonaPreset | null;
  editorScope: "user" | "global";
  canAdmin: boolean;
  isMutating: boolean;
  createPreset: (data: PersonaPresetCreate) => Promise<PersonaPreset | null>;
  updatePreset: (
    presetId: string,
    data: PersonaPresetUpdate,
  ) => Promise<PersonaPreset | null>;
  onClose: () => void;
}

export const PERSONA_SKILL_PAGE_SIZE = 20;

export const AVATAR_EMOJIS: { emoji: string; labelKey: string }[] = [
  { emoji: "✨", labelKey: "personaPresets.emojiSparkles" },
  { emoji: "🤖", labelKey: "personaPresets.emojiRobot" },
  { emoji: "🎓", labelKey: "personaPresets.emojiAcademic" },
  { emoji: "💻", labelKey: "personaPresets.emojiCoding" },
  { emoji: "✍️", labelKey: "personaPresets.emojiWriting" },
  { emoji: "🛡️", labelKey: "personaPresets.emojiSecurity" },
  { emoji: "📊", labelKey: "personaPresets.emojiData" },
  { emoji: "⚡", labelKey: "personaPresets.emojiProductivity" },
  { emoji: "📦", labelKey: "personaPresets.emojiGeneral" },
  { emoji: "🎨", labelKey: "personaPresets.emojiArt" },
  { emoji: "🎵", labelKey: "personaPresets.emojiMusic" },
  { emoji: "📚", labelKey: "personaPresets.emojiLiterature" },
  { emoji: "🧠", labelKey: "personaPresets.emojiIntelligence" },
  { emoji: "🔬", labelKey: "personaPresets.emojiScience" },
  { emoji: "💬", labelKey: "personaPresets.emojiChat" },
  { emoji: "🌟", labelKey: "personaPresets.emojiStar" },
];
