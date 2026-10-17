import type { TFunction } from "i18next";
import i18n from "../../../i18n";
import {
  Bot,
  Palette,
  Code2,
  FlaskConical,
  Search,
  PenTool,
  Database,
  ShieldCheck,
  Star,
  type LucideIcon,
} from "lucide-react";
import {
  getEmojiAvatarUrl,
  isEmojiAvatar,
  isPersonaImageAvatar,
} from "../../persona/personaAvatar";
import { getFullUrl } from "../../../services/api/config";

export type SubagentRoleIconKind =
  | "design"
  | "code"
  | "test"
  | "research"
  | "writing"
  | "data"
  | "review"
  | "grading"
  | "general";

export type SubagentRoleIconMeta = {
  kind: SubagentRoleIconKind;
  icon: LucideIcon;
  className: string;
  bgClassName: string;
  emoji?: string;
};

const SUBAGENT_ROLE_ICON_META: Record<
  SubagentRoleIconKind,
  SubagentRoleIconMeta
> = {
  design: {
    kind: "design",
    icon: Palette,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  code: {
    kind: "code",
    icon: Code2,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  test: {
    kind: "test",
    icon: FlaskConical,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  research: {
    kind: "research",
    icon: Search,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  writing: {
    kind: "writing",
    icon: PenTool,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  data: {
    kind: "data",
    icon: Database,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  review: {
    kind: "review",
    icon: ShieldCheck,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  grading: {
    kind: "grading",
    icon: Star,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
    emoji: "⭐",
  },
  general: {
    kind: "general",
    icon: Bot,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
    emoji: "🤖",
  },
};

export function formatSubagentName(agentName: string): string {
  if (/^rubric[ _]grader$/i.test(agentName)) {
    return i18n.t("chat.message.rubricGraderName");
  }
  return agentName
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function formatSubagentInput(
  agentName: string,
  input: string,
  t: TFunction = i18n.t,
): string {
  return /^rubric[ _]grader$/i.test(agentName) &&
    input === "Evaluating against rubric criteria"
    ? t("chat.message.rubricGraderInput")
    : input;
}

export function getSubagentRoleIconMeta(
  agentName: string,
): SubagentRoleIconMeta {
  const name = agentName.toLowerCase();
  if (/(设计|design|视觉|ui|ux|brand|creative)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.design;
  }
  if (
    /(code|coding|dev|developer|engineer|frontend|backend|程序|开发|工程)/i.test(
      name,
    )
  ) {
    return SUBAGENT_ROLE_ICON_META.code;
  }
  if (/(test|qa|quality|验收|测试)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.test;
  }
  if (/(research|search|investigate|analysis|分析|研究|调研)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.research;
  }
  if (/(write|writer|copy|content|editor|文案|写作|编辑)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.writing;
  }
  if (/(data|database|db|analytics|数据)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.data;
  }
  if (/(review|security|audit|critic|审查|审核|安全)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.review;
  }
  if (/(rubric|grading|grader|评分|评审)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.grading;
  }
  return SUBAGENT_ROLE_ICON_META.general;
}

export function getSubagentAvatarImageUrl(
  avatar: string | null | undefined,
): string | null {
  if (isEmojiAvatar(avatar)) {
    return getEmojiAvatarUrl(avatar);
  }
  if (isPersonaImageAvatar(avatar)) {
    return getFullUrl(avatar) ?? avatar;
  }
  return null;
}
