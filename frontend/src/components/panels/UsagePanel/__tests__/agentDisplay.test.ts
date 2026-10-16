import { createInstance } from "i18next";
import { resolveAgentReferenceName } from "../../../agent/agentCatalog";
import type { AgentInfo } from "../../../../types";

import zh from "../../../../i18n/locales/zh.json";
import en from "../../../../i18n/locales/en.json";

const i18n = createInstance();
await i18n.init({
  lng: "zh",
  resources: { zh: { translation: zh }, en: { translation: en } },
});
const agents: AgentInfo[] = [
  {
    id: "search",
    name: "Search Agent",
    description: "Research",
    version: "1",
    labels: {
      zh: { name: "研究助手", description: "研究" },
      en: { name: "Research Agent", description: "Research" },
    },
  },
];

test("usage logs and rankings resolve catalog names by id or stored English name", () => {
  expect(
    resolveAgentReferenceName("search", "Old name", agents, "zh-CN", i18n.t),
  ).toBe("研究助手");
  expect(
    resolveAgentReferenceName(
      undefined,
      "Search Agent",
      agents,
      "zh-CN",
      i18n.t,
    ),
  ).toBe("研究助手");
  expect(
    resolveAgentReferenceName(
      "Search Agent",
      "Search Agent",
      agents,
      "zh-CN",
      i18n.t,
    ),
  ).toBe("研究助手");
});

test("uses the shared locale fallback when no catalog label exists", () => {
  expect(
    resolveAgentReferenceName(
      "search",
      "Search Agent",
      [{ ...agents[0], labels: {} }],
      "zh",
      i18n.t,
    ),
  ).toBe("探索助手");
  expect(
    resolveAgentReferenceName("search", "Search Agent", [], "zh", i18n.t),
  ).toBe("探索助手");
});

test("preserves unknown historical names and empty values", () => {
  expect(
    resolveAgentReferenceName("deleted", "Custom Agent", agents, "zh", i18n.t),
  ).toBe("Custom Agent");
  expect(
    resolveAgentReferenceName(undefined, "Rubric Grader", agents, "zh", i18n.t),
  ).toBe("Rubric Grader");
  expect(resolveAgentReferenceName(undefined, "", agents, "zh", i18n.t)).toBe(
    "",
  );
});

test("language changes use the corresponding catalog label", () => {
  expect(
    resolveAgentReferenceName("search", "Search Agent", agents, "en", i18n.t),
  ).toBe("Research Agent");
});

test("localizes historical built-in names even when the catalog is unavailable", () => {
  for (const [name, label] of [
    ["Search Agent", "探索助手"],
    ["Team Agent", "团队助手"],
    ["Fast Agent", "快速助手"],
    ["Everyday Assistant", "轻量助手"],
  ]) {
    expect(resolveAgentReferenceName(name, name, [], "zh", i18n.t)).toBe(label);
    expect(resolveAgentReferenceName(undefined, name, [], "zh", i18n.t)).toBe(
      label,
    );
  }
});
