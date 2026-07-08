import assert from "node:assert/strict";
import test from "node:test";
import {
  firstEffectivePluginOptionPath,
  filterPluginOptionsByVisibleWhen,
  hasEffectiveCorePersonaSuppressingOption,
  pluginOptionFromMetadata,
  pluginOptionFromValues,
  pluginOptionPathFromDeclaration,
  retainPluginOptionsForDeclarations,
  pluginOptionsFromMetadata,
  selectedAgentTeamIdFromMetadata,
  withPluginOption,
} from "../pluginOptions";

const AGENT_TEAM_PLUGIN_ID = "agent_team";
const AGENT_TEAM_SELECTED_TEAM_OPTION = "SELECTED_TEAM_ID";

test("plugin option helpers read namespaced Agent Team session options", () => {
  const metadata = {
    team_id: "legacy-team",
    plugin_options: {
      [AGENT_TEAM_PLUGIN_ID]: {
        [AGENT_TEAM_SELECTED_TEAM_OPTION]: "plugin-team",
      },
    },
  };

  assert.equal(
    pluginOptionFromMetadata(
      metadata,
      AGENT_TEAM_PLUGIN_ID,
      AGENT_TEAM_SELECTED_TEAM_OPTION,
    ),
    "plugin-team",
  );
  assert.equal(selectedAgentTeamIdFromMetadata(metadata), "plugin-team");
});

test("plugin option helpers keep legacy team_id as read-only fallback", () => {
  assert.equal(
    selectedAgentTeamIdFromMetadata({ team_id: "legacy-team" }),
    "legacy-team",
  );
  assert.equal(selectedAgentTeamIdFromMetadata({ team_id: "" }), null);
  assert.equal(selectedAgentTeamIdFromMetadata(null), null);
});

test("plugin option writer updates one namespace without dropping other plugins", () => {
  const metadata = withPluginOption(
    {
      plugin_options: {
        other_plugin: { KEEP: true },
        agent_team: { SELECTED_TEAM_ID: "old-team" },
      },
    },
    "agent_team",
    "SELECTED_TEAM_ID",
    "team-1",
  );

  assert.deepEqual(pluginOptionsFromMetadata(metadata), {
    other_plugin: { KEEP: true },
    agent_team: { SELECTED_TEAM_ID: "team-1" },
  });

  assert.deepEqual(
    withPluginOption(metadata, "agent_team", "SELECTED_TEAM_ID", null),
    { plugin_options: { other_plugin: { KEEP: true } } },
  );
});

test("generic plugin option helpers resolve declared option paths", () => {
  const options = {
    agent_team: { SELECTED_TEAM_ID: "team-1" },
    reporter: { WINDOW_DAYS: 30 },
  };

  assert.equal(pluginOptionFromValues(options, "reporter", "WINDOW_DAYS"), 30);
  assert.deepEqual(
    pluginOptionPathFromDeclaration({ plugin_id: "reporter", key: "WINDOW_DAYS" }),
    { pluginId: "reporter", key: "WINDOW_DAYS" },
  );
  assert.deepEqual(
    pluginOptionPathFromDeclaration({ pluginId: "reporter", key: "WINDOW_DAYS" }),
    { pluginId: "reporter", key: "WINDOW_DAYS" },
  );
  assert.deepEqual(
    firstEffectivePluginOptionPath([
      { plugin_id: "disabled", key: "VALUE", effective: false },
      { plugin_id: "reporter", key: "WINDOW_DAYS", effective: true },
    ], { effectiveOnly: true }),
    { pluginId: "reporter", key: "WINDOW_DAYS" },
  );
  assert.equal(
    firstEffectivePluginOptionPath([
      { plugin_id: "disabled", key: "VALUE", effective: false },
    ], { effectiveOnly: true }),
    null,
  );
});

test("generic plugin option helpers filter by safe visible_when declarations", () => {
  const options = [
    {
      plugin_id: "agent_team",
      key: "SELECTED_TEAM_ID",
      visible_when: { agent_id: "team", route: "/channels/feishu" },
    },
    {
      plugin_id: "reporter",
      key: "WINDOW_DAYS",
      visible_when: { route: "/channels/feishu" },
    },
    {
      plugin_id: "other",
      key: "MODE",
      visible_when: { agent_id: "research" },
    },
  ];

  assert.deepEqual(
    filterPluginOptionsByVisibleWhen(options, {
      agentId: "team",
      route: "/channels/feishu",
      scope: "channel",
    }).map((option) => `${option.plugin_id}.${option.key}`),
    ["agent_team.SELECTED_TEAM_ID", "reporter.WINDOW_DAYS"],
  );
  assert.deepEqual(
    filterPluginOptionsByVisibleWhen(options, {
      agentId: "chat",
      route: "/channels/feishu",
      scope: "channel",
    }).map((option) => `${option.plugin_id}.${option.key}`),
    ["reporter.WINDOW_DAYS"],
  );
});

test("generic plugin option helpers retain only currently declared option values", () => {
  const values = {
    agent_team: { SELECTED_TEAM_ID: "team-1", STALE: "remove" },
    reporter: { WINDOW_DAYS: 30 },
  };

  assert.deepEqual(
    retainPluginOptionsForDeclarations(values, [
      { plugin_id: "agent_team", key: "SELECTED_TEAM_ID" },
      { plugin_id: "reporter", key: "WINDOW_DAYS" },
    ]),
    {
      agent_team: { SELECTED_TEAM_ID: "team-1" },
      reporter: { WINDOW_DAYS: 30 },
    },
  );
  assert.deepEqual(retainPluginOptionsForDeclarations(values, []), {});
});

test("generic plugin option helpers detect persona suppressing declarations", () => {
  assert.equal(
    hasEffectiveCorePersonaSuppressingOption([
      {
        plugin_id: "agent_team",
        key: "SELECTED_TEAM_ID",
        effective: true,
        suppresses_core_persona_selector: true,
      },
    ]),
    true,
  );
  assert.equal(
    hasEffectiveCorePersonaSuppressingOption([
      {
        plugin_id: "agent_team",
        key: "SELECTED_TEAM_ID",
        effective: false,
        suppresses_core_persona_selector: true,
      },
    ]),
    false,
  );
});

test("generic plugin option helpers replace Agent Team-specific path helpers", () => {
  const declarations = [
    {
      plugin_id: AGENT_TEAM_PLUGIN_ID,
      key: AGENT_TEAM_SELECTED_TEAM_OPTION,
      effective: false,
    },
    {
      plugin_id: "other_plugin",
      key: "SELECTED_ITEM_ID",
      effective: true,
    },
  ];

  assert.deepEqual(
    pluginOptionPathFromDeclaration(declarations[0]),
    { pluginId: AGENT_TEAM_PLUGIN_ID, key: AGENT_TEAM_SELECTED_TEAM_OPTION },
  );
  assert.deepEqual(
    firstEffectivePluginOptionPath(declarations, { effectiveOnly: true }),
    { pluginId: "other_plugin", key: "SELECTED_ITEM_ID" },
  );
});
