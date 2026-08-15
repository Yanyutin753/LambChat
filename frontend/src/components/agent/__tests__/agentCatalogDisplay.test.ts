import {
  resolveAgentDescription,
  resolveAgentDisplayName,
} from "../agentCatalog";

const translations: Record<string, string> = {
  "agents.search.name": "Агент поиска",
  "agents.search.description": "С интерпретатором кода и песочницей",
};

const t = ((key: string, defaultValue?: string) =>
  translations[key] ?? defaultValue ?? `i18n:${key}`) as unknown as Parameters<
  typeof resolveAgentDisplayName
>[2];

const agent = {
  id: "search",
  name: "Search Agent",
  description: "For research and complex tasks",
  labels: {
    zh: {
      name: "搜索助手",
      description: "面向检索和复杂任务",
    },
    en: {
      name: "Research Agent",
      description: "For research and complex tasks",
    },
  },
};

test("resolves agent display metadata from the current locale", () => {
  expect(resolveAgentDisplayName(agent, "zh-CN", t)).toBe("搜索助手");
  expect(resolveAgentDescription(agent, "zh-CN", t)).toBe("面向检索和复杂任务");
});

test("falls back to i18n translation when current locale has no label", () => {
  // ru has no label → i18n key "agents.search.name" → "Агент поиска"
  expect(resolveAgentDisplayName(agent, "ru", t)).toBe("Агент поиска");
  expect(resolveAgentDescription(agent, "ru", t)).toBe(
    "С интерпретатором кода и песочницей",
  );
});

test("falls back to i18n key when no labels are configured", () => {
  // labels empty → t("agents.search.name", "Search Agent") → "Агент поиска"
  expect(resolveAgentDisplayName({ ...agent, labels: {} }, "ru", t)).toBe(
    "Агент поиска",
  );
  expect(resolveAgentDescription({ ...agent, labels: {} }, "ru", t)).toBe(
    "С интерпретатором кода и песочницей",
  );
});

test("falls back to raw name when agent has no id and no labels", () => {
  const noIdAgent = { ...agent, id: undefined, labels: {} };
  // no id → t("Search Agent") without defaultValue → "i18n:Search Agent"
  expect(resolveAgentDisplayName(noIdAgent, "ru", t)).toBe("i18n:Search Agent");
});
