import {
  resolveAgentDescription,
  resolveAgentDisplayName,
  resolveAgentReferenceName,
  resolveAssistantIdentityDisplay,
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

test("recorded built-in names are localized without an authenticated catalog", () => {
  expect(resolveAgentReferenceName(undefined, "Search Agent", [], "ru", t)).toBe("Агент поиска");
  expect(resolveAgentReferenceName("search", "Old name", [], "ru", t)).toBe("Агент поиска");
  expect(resolveAgentReferenceName(undefined, "Deleted custom agent", [], "ru", t)).toBe("Deleted custom agent");
});

test("legacy English rankings use the current catalog even after its fallback name was renamed", () => {
  expect(resolveAgentReferenceName("Search Agent", "Search Agent", [
    { ...agent, name: "Renamed", version: "1", labels: { ru: { name: "Исследователь", description: "" } } },
  ], "ru", t)).toBe("Исследователь");
});

test("plain-agent identities follow the current catalog instead of the frozen snapshot", () => {
  const catalog = [{ ...agent, name: "全能 Agent", version: "1", icon: "generated:avatar-5" }];
  // run 提交时冻结的旧名/旧头像不再决定展示：跟随目录标签与 icon
  expect(
    resolveAssistantIdentityDisplay(
      { seed: "search", name: "全能 Agent", avatar: "generated:avatar-9" },
      catalog,
      "zh-CN",
      t,
    ),
  ).toEqual({ name: "搜索助手", avatar: "generated:avatar-5", seed: "search" });
});

test("plain-agent identities fall back to built-in translations without a catalog", () => {
  expect(
    resolveAssistantIdentityDisplay(
      { seed: "search", name: "agents.search.name", avatar: null },
      [],
      "ru",
      t,
    ),
  ).toEqual({ name: "Агент поиска", avatar: null, seed: "search" });
});

test("persona and team identities keep their per-run snapshot", () => {
  expect(
    resolveAssistantIdentityDisplay(
      { seed: "preset-42", name: "写作搭子", avatar: "😀" },
      [{ ...agent, name: "Search Agent", version: "1" }],
      "zh-CN",
      t,
    ),
  ).toEqual({ name: "写作搭子", avatar: "😀", seed: "preset-42" });
});
