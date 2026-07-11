import {
  resolveAvailableAgentId,
  resolvePersonaAgentId,
} from "../agentSelection";

const agents = [
  { id: "search", name: "Search", description: "", version: "1.0.0" },
  { id: "fast", name: "Fast", description: "", version: "1.0.0" },
];

test("falls back to the first available agent when the default agent is unavailable", () => {
  expect(resolveAvailableAgentId("", "default", agents)).toBe("search");
});

test("keeps the current agent when it is still available", () => {
  expect(resolveAvailableAgentId("fast", "search", agents)).toBe("fast");
});

test("replaces an unavailable current agent with the first available agent", () => {
  expect(resolveAvailableAgentId("default", "default", agents)).toBe("search");
});

test("persona mode keeps the current non-plugin agent", () => {
  expect(resolvePersonaAgentId("fast", "search", agents)).toBe("fast");
});

test("persona mode switches an excluded plugin agent to the preferred non-plugin default", () => {
  expect(resolvePersonaAgentId("team", "fast", [
      { id: "team", name: "Team", description: "", version: "1.0.0" },
      ...agents,
    ], ["team"])).toBe("fast");
});

test("persona mode switches an excluded plugin agent to the first non-plugin agent when needed", () => {
  expect(resolvePersonaAgentId("team", "team", [
      { id: "team", name: "Team", description: "", version: "1.0.0" },
      ...agents,
    ], ["team"])).toBe("search");
});

test("persona mode can exclude any plugin-owned agent id", () => {
  expect(resolvePersonaAgentId("plugin_agent", "plugin_agent", [
      { id: "plugin_agent", name: "Plugin Agent", description: "", version: "1.0.0" },
      ...agents,
    ], ["plugin_agent"])).toBe("search");
});
