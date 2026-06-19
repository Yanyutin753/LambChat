import test from "node:test";
import assert from "node:assert/strict";
import {
  resolveAvailableAgentId,
  resolvePersonaAgentId,
} from "../agentSelection";

const agents = [
  { id: "search", name: "Search", description: "", version: "1.0.0" },
  { id: "fast", name: "Fast", description: "", version: "1.0.0" },
];

test("falls back to the first available agent when the default agent is unavailable", () => {
  assert.equal(resolveAvailableAgentId("", "default", agents), "search");
});

test("keeps the current agent when it is still available", () => {
  assert.equal(resolveAvailableAgentId("fast", "search", agents), "fast");
});

test("replaces an unavailable current agent with the first available agent", () => {
  assert.equal(resolveAvailableAgentId("default", "default", agents), "search");
});

test("persona mode keeps the current non-plugin agent", () => {
  assert.equal(resolvePersonaAgentId("fast", "search", agents), "fast");
});

test("persona mode switches an excluded plugin agent to the preferred non-plugin default", () => {
  assert.equal(
    resolvePersonaAgentId("team", "fast", [
      { id: "team", name: "Team", description: "", version: "1.0.0" },
      ...agents,
    ], ["team"]),
    "fast",
  );
});

test("persona mode switches an excluded plugin agent to the first non-plugin agent when needed", () => {
  assert.equal(
    resolvePersonaAgentId("team", "team", [
      { id: "team", name: "Team", description: "", version: "1.0.0" },
      ...agents,
    ], ["team"]),
    "search",
  );
});

test("persona mode can exclude any plugin-owned agent id", () => {
  assert.equal(
    resolvePersonaAgentId("workflow", "workflow", [
      { id: "workflow", name: "Workflow", description: "", version: "1.0.0" },
      ...agents,
    ], ["workflow"]),
    "search",
  );
});
