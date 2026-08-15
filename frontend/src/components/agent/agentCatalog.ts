import type { TFunction } from "i18next";
import type { AgentCatalogLabels } from "../../types";

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
  labels?: AgentCatalogLabels;
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
