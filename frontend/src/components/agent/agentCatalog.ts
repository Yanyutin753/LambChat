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
