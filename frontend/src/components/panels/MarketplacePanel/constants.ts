import {
  GraduationCap,
  Code2,
  PenTool,
  Shield,
  Database,
  Zap,
  Package,
  type LucideIcon,
} from "lucide-react";

// Deterministic gradient pairs for card banners
export const GRADIENT_PALETTES = [
  ["#c7a16b", "#90bcd5", "#c1b5e3"],
  ["#846bc7", "#d590a8", "#d5b5e3"],
  ["#7766cc", "#8c95d9", "#bcb3e6"],
  ["#82a9c9", "#d1c994", "#d8d9a6"],
  ["#cc66b9", "#8cd9d5", "#c9b3e6"],
  ["#b1b87a", "#9cc9a2", "#d0bddb"],
  ["#c6c982", "#d1cf94", "#d2d9a6"],
  ["#c98e82", "#d1c294", "#c0d9a6"],
  ["#a68bc7", "#b5c7d5", "#d9c4e3"],
  ["#7ab8a2", "#c9c082", "#d5b5c7"],
  ["#c7946b", "#a8c790", "#c9a8d5"],
  ["#8b7ac7", "#d5a08c", "#a8d5c9"],
];

// Category icon mapping based on tag keywords
export function getCategoryIcon(tag: string): LucideIcon {
  const t = tag.toLowerCase();
  if (
    t.includes("学术") ||
    t.includes("academic") ||
    t.includes("论文") ||
    t.includes("paper")
  )
    return GraduationCap;
  if (
    t.includes("编程") ||
    t.includes("coding") ||
    t.includes("code") ||
    t.includes("dev")
  )
    return Code2;
  if (
    t.includes("文案") ||
    t.includes("writing") ||
    t.includes("copy") ||
    t.includes("writer")
  )
    return PenTool;
  if (t.includes("安全") || t.includes("security") || t.includes("安全"))
    return Shield;
  if (
    t.includes("数据") ||
    t.includes("data") ||
    t.includes("数据库") ||
    t.includes("database")
  )
    return Database;
  if (
    t.includes("效率") ||
    t.includes("productivity") ||
    t.includes("工具") ||
    t.includes("tool")
  )
    return Zap;
  return Package;
}

// Deterministic hash for gradient selection
export function nameToGradient(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return GRADIENT_PALETTES[Math.abs(hash) % GRADIENT_PALETTES.length];
}
