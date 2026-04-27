import { Brain, Zap, Settings, type LucideIcon } from "lucide-react";

export const ICON_MAP: Record<string, LucideIcon> = {
  Brain,
  Zap,
  Settings,
};

/** When pasted text exceeds this length, auto-convert to a .txt file upload. */
export const PASTE_TEXT_THRESHOLD = 3000;

export const THINKING_LEVEL_COLOR: Record<
  string,
  { border: string; bg: string; text: string }
> = {
  off: {
    border: "transparent",
    bg: "transparent",
    text: "var(--theme-text-secondary)",
  },
  low: {
    border: "color-mix(in srgb, #60a5fa 40%, transparent)",
    bg: "color-mix(in srgb, #60a5fa 10%, transparent)",
    text: "#60a5fa",
  },
  medium: {
    border: "color-mix(in srgb, #fbbf24 40%, transparent)",
    bg: "color-mix(in srgb, #fbbf24 10%, transparent)",
    text: "#fbbf24",
  },
  high: {
    border: "color-mix(in srgb, #fb923c 40%, transparent)",
    bg: "color-mix(in srgb, #fb923c 10%, transparent)",
    text: "#fb923c",
  },
  max: {
    border: "color-mix(in srgb, #f472b6 40%, transparent)",
    bg: "color-mix(in srgb, #f472b6 10%, transparent)",
    text: "#f472b6",
  },
};
