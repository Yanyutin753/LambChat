import {
  resolveAgentDescription,
  resolveAgentDisplayName,
} from "../agentCatalog";

const t = (key: string) => `i18n:${key}`;

const agent = {
  id: "search",
  name: "agents.search.name",
  description: "agents.search.description",
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

test("falls back through configured languages before legacy i18n keys", () => {
  expect(resolveAgentDisplayName(agent, "ja", t)).toBe("搜索助手");
  expect(resolveAgentDescription({ ...agent, labels: {} }, "ja", t)).toBe(
    "i18n:agents.search.description",
  );
});
