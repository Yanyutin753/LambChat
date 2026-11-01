import type { TFunction } from "i18next";
import type { AgentCatalogLocale, AgentInfo } from "../../types";
import en from "../../i18n/locales/en.json";

export const AGENT_CATALOG_LOCALES = [
  { code: "zh", label: "中文" },
  { code: "en", label: "English" },
  { code: "ja", label: "日本語" },
  { code: "ko", label: "한국어" },
  { code: "ru", label: "Русский" },
] as const;

type AgentDisplaySource = {
  id?: string;
  name: string;
  description: string;
  labels?: Record<string, Partial<AgentCatalogLocale>>;
};

type Translate = TFunction;

function normalizeLocale(locale?: string) {
  return (locale || "en").split("-")[0].toLowerCase();
}

function resolveLocalizedField(
  agent: AgentDisplaySource,
  locale: string | undefined,
  field: "name" | "description",
  fallbackKey: string,
  t: Translate,
) {
  const labels = agent.labels || {};
  const currentLocale = normalizeLocale(locale);
  const value = labels[currentLocale]?.[field]?.trim();
  if (value) return value;
  const i18nKey = agent.id ? `agents.${agent.id}.${field}` : undefined;
  return i18nKey ? t(i18nKey, fallbackKey) : t(fallbackKey);
}

export function resolveAgentDisplayName(
  agent: AgentDisplaySource,
  locale: string | undefined,
  t: Translate,
) {
  return resolveLocalizedField(agent, locale, "name", agent.name, t);
}

export function resolveAgentDescription(
  agent: AgentDisplaySource,
  locale: string | undefined,
  t: Translate,
) {
  return resolveLocalizedField(
    agent,
    locale,
    "description",
    agent.description,
    t,
  );
}

/** Resolve stored names and IDs, including public pages without a loaded catalog. */
export function resolveAgentReferenceName(
  id: string | undefined,
  name: string,
  agents: readonly AgentInfo[],
  locale: string,
  t: Translate,
  labels?: AgentDisplaySource["labels"],
): string {
  const legacyId = Object.entries(en.agents).find(([key, value]) =>
    name === value.name || name === key || name === `agents.${key}.name`,
  )?.[0];
  const agentId = legacyId && (!id || id === name) ? legacyId : id;
  if (labels && Object.keys(labels).length) {
    return resolveAgentDisplayName({ id: agentId, name, description: "", labels }, locale, t);
  }
  const agent = agents.find((item) => item.id === id || item.id === name)
    ?? agents.find((item) => item.name === name)
    ?? agents.find((item) => item.id === legacyId);
  if (agent) return resolveAgentDisplayName(agent, locale, t);
  return agentId ? t(`agents.${agentId}.name`, name || agentId) : name;
}

export const BUILT_IN_AGENT_IDS: readonly string[] = Object.keys(en.agents);

type AssistantIdentityLike = {
  seed?: string | null;
  name?: string | null;
  avatar?: string | null;
};

/**
 * 判定 run 身份是否指向普通 agent（seed 是 agent id 或旧快照名是
 * `agents.<id>.name` 形态）。persona（seed=preset_id）与团队（seed=队名）
 * 的身份按 run 冻结，不在此列。
 */
export function findPlainAgentEntry(
  identity: AssistantIdentityLike | undefined,
  agents: readonly AgentInfo[],
): AgentInfo | undefined {
  if (!identity) return undefined;
  const seed = identity.seed?.trim() || "";
  const bySeed = agents.find((item) => item.id === seed);
  if (bySeed) return bySeed;
  const keyMatch = /^agents\.([a-z0-9_-]+)\.name$/i.exec(identity.name || "");
  const agentId = keyMatch?.[1] || seed;
  if (!BUILT_IN_AGENT_IDS.includes(agentId)) return undefined;
  return (
    agents.find((item) => item.id === agentId) ?? {
      id: agentId,
      name: `agents.${agentId}.name`,
      description: "",
      version: "",
    }
  );
}

/**
 * 渲染时解析 assistant 身份的展示名与头像。普通 agent 跟随当前目录
 * （含本地化标签与头像，管理端改名后新旧消息一致），其余身份沿用
 * run 提交时的快照，避免历史消息名/头像与站内来回跳变。
 */
export function resolveAssistantIdentityDisplay(
  identity: AssistantIdentityLike | undefined,
  agents: readonly AgentInfo[],
  locale: string | undefined,
  t: Translate,
): { name: string | null; avatar: string | null; seed: string } {
  if (!identity) return { name: null, avatar: null, seed: "agent" };
  const seed = identity.seed?.trim() || "agent";
  const entry = findPlainAgentEntry(identity, agents);
  if (entry) {
    return {
      name: resolveAgentDisplayName(entry, locale, t),
      avatar: entry.icon ?? null,
      seed,
    };
  }
  return { name: identity.name ?? null, avatar: identity.avatar ?? null, seed };
}
