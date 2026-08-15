import {
  resolveAgentDescription,
  resolveAgentDisplayName,
} from "../agentCatalog";

const t = (key: string, defaultValue?: string) => defaultValue ?? `i18n:${key}`;

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

test("falls back to i18n key when current locale has no label", () => {
  // ja has no label → skips to i18n key → t("agents.search.name", "Search Agent")
  expect(resolveAgentDisplayName(agent, "ja", t)).toBe("Search Agent");
});

test("falls back to i18n key when no labels are configured", () => {
  // labels empty → falls back to t("agents.search.name", "Search Agent")
  expect(resolveAgentDisplayName({ ...agent, labels: {} }, "ja", t)).toBe(
    "Search Agent",
  );
  expect(resolveAgentDescription({ ...agent, labels: {} }, "ja", t)).toBe(
    "For research and complex tasks",
  );
});

test("falls back to raw name when agent has no id and no labels", () => {
  const noIdAgent = { ...agent, id: undefined, labels: {} };
  // no id → t("Search Agent") without defaultValue → "i18n:Search Agent"
  expect(resolveAgentDisplayName(noIdAgent, "ja", t)).toBe("i18n:Search Agent");
});
