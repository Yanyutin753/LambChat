export type PersonaAvatarIconKey =
  | "sparkles"
  | "academic"
  | "coding"
  | "writing"
  | "security"
  | "data"
  | "productivity"
  | "general";

export interface PersonaAvatarIconMeta {
  key: PersonaAvatarIconKey;
  label: string;
  color: string;
  bg: string;
}

export const PERSONA_AVATAR_ICON_PREFIX = "icon:";

const PERSONA_AVATAR_ICONS: PersonaAvatarIconMeta[] = [
  { key: "sparkles", label: "Sparkles", color: "#6366f1", bg: "#eef2ff" },
  { key: "academic", label: "Academic", color: "#0891b2", bg: "#ecfeff" },
  { key: "coding", label: "Coding", color: "#16a34a", bg: "#f0fdf4" },
  { key: "writing", label: "Writing", color: "#c026d3", bg: "#fdf4ff" },
  { key: "security", label: "Security", color: "#dc2626", bg: "#fef2f2" },
  { key: "data", label: "Data", color: "#ea580c", bg: "#fff7ed" },
  {
    key: "productivity",
    label: "Productivity",
    color: "#ca8a04",
    bg: "#fefce8",
  },
  { key: "general", label: "General", color: "#4f46e5", bg: "#eef2ff" },
];

export function getPersonaAvatarIcons(): PersonaAvatarIconMeta[] {
  return PERSONA_AVATAR_ICONS;
}

export function getPersonaAvatarIconValue(key: PersonaAvatarIconKey): string {
  return `${PERSONA_AVATAR_ICON_PREFIX}${key}`;
}

export function getPersonaAvatarIcon(
  avatar: string | null | undefined,
): PersonaAvatarIconMeta | null {
  if (!avatar?.startsWith(PERSONA_AVATAR_ICON_PREFIX)) return null;
  const key = avatar.slice(
    PERSONA_AVATAR_ICON_PREFIX.length,
  ) as PersonaAvatarIconKey;
  return PERSONA_AVATAR_ICONS.find((icon) => icon.key === key) ?? null;
}

export function isPersonaImageAvatar(
  avatar: string | null | undefined,
): avatar is string {
  return !!avatar && !avatar.startsWith(PERSONA_AVATAR_ICON_PREFIX);
}
