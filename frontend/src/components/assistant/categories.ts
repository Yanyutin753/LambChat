import {
  Code,
  PenLine,
  Languages,
  GraduationCap,
  Briefcase,
  Palette,
  BarChart3,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

export interface AssistantCategory {
  id: string;
  label: string;
  icon: LucideIcon;
}

export const ASSISTANT_CATEGORIES: AssistantCategory[] = [
  { id: "programming", label: "Programming", icon: Code },
  { id: "writing", label: "Writing", icon: PenLine },
  { id: "translation", label: "Translation", icon: Languages },
  { id: "education", label: "Education", icon: GraduationCap },
  { id: "business", label: "Business", icon: Briefcase },
  { id: "creative", label: "Creative", icon: Palette },
  { id: "analysis", label: "Analysis", icon: BarChart3 },
  { id: "general", label: "General", icon: Sparkles },
];

export const CATEGORY_MAP = new Map(
  ASSISTANT_CATEGORIES.map((cat) => [cat.id, cat]),
);

export function getCategoryById(id: string): AssistantCategory | undefined {
  return CATEGORY_MAP.get(id);
}
