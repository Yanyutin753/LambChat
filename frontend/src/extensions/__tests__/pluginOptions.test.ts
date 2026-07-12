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

  expect(pluginOptionFromMetadata(
      metadata,
      AGENT_TEAM_PLUGIN_ID,
      AGENT_TEAM_SELECTED_TEAM_OPTION,
    )).toBe("plugin-team");
  expect(selectedAgentTeamIdFromMetadata(metadata)).toBe("plugin-team");
});

test("plugin option helpers keep legacy team_id as read-only fallback", () => {
  expect(selectedAgentTeamIdFromMetadata({ team_id: "legacy-team" })).toBe("legacy-team");
  expect(selectedAgentTeamIdFromMetadata({ team_id: "" })).toBe(null);
  expect(selectedAgentTeamIdFromMetadata(null)).toBe(null);
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

  expect(pluginOptionsFromMetadata(metadata)).toEqual({
    other_plugin: { KEEP: true },
    agent_team: { SELECTED_TEAM_ID: "team-1" },
  });

  expect(withPluginOption(metadata, "agent_team", "SELECTED_TEAM_ID", null)).toEqual({ plugin_options: { other_plugin: { KEEP: true } } });
});

test("generic plugin option helpers resolve declared option paths", () => {
  const options = {
    agent_team: { SELECTED_TEAM_ID: "team-1" },
    reporter: { WINDOW_DAYS: 30 },
  };

  expect(pluginOptionFromValues(options, "reporter", "WINDOW_DAYS")).toBe(30);
  expect(pluginOptionPathFromDeclaration({ plugin_id: "reporter", key: "WINDOW_DAYS" })).toEqual({ pluginId: "reporter", key: "WINDOW_DAYS" });
  expect(pluginOptionPathFromDeclaration({ pluginId: "reporter", key: "WINDOW_DAYS" })).toEqual({ pluginId: "reporter", key: "WINDOW_DAYS" });
  expect(firstEffectivePluginOptionPath([
      { plugin_id: "disabled", key: "VALUE", effective: false },
      { plugin_id: "reporter", key: "WINDOW_DAYS", effective: true },
    ], { effectiveOnly: true })).toEqual({ pluginId: "reporter", key: "WINDOW_DAYS" });
  expect(firstEffectivePluginOptionPath([
      { plugin_id: "disabled", key: "VALUE", effective: false },
    ], { effectiveOnly: true })).toBe(null);
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

  expect(filterPluginOptionsByVisibleWhen(options, {
      agentId: "team",
      route: "/channels/feishu",
      scope: "channel",
    }).map((option) => `${option.plugin_id}.${option.key}`)).toEqual(["agent_team.SELECTED_TEAM_ID", "reporter.WINDOW_DAYS"]);
  expect(filterPluginOptionsByVisibleWhen(options, {
      agentId: "chat",
      route: "/channels/feishu",
      scope: "channel",
    }).map((option) => `${option.plugin_id}.${option.key}`)).toEqual(["reporter.WINDOW_DAYS"]);
});

test("generic plugin option helpers retain only currently declared option values", () => {
  const values = {
    agent_team: { SELECTED_TEAM_ID: "team-1", STALE: "remove" },
    reporter: { WINDOW_DAYS: 30 },
  };

  expect(retainPluginOptionsForDeclarations(values, [
      { plugin_id: "agent_team", key: "SELECTED_TEAM_ID" },
      { plugin_id: "reporter", key: "WINDOW_DAYS" },
    ])).toEqual({
      agent_team: { SELECTED_TEAM_ID: "team-1" },
      reporter: { WINDOW_DAYS: 30 },
    });
  expect(retainPluginOptionsForDeclarations(values, [])).toEqual({});
});

test("generic plugin option helpers detect persona suppressing declarations", () => {
  expect(hasEffectiveCorePersonaSuppressingOption([
      {
        plugin_id: "agent_team",
        key: "SELECTED_TEAM_ID",
        effective: true,
        suppresses_core_persona_selector: true,
      },
    ])).toBe(true);
  expect(hasEffectiveCorePersonaSuppressingOption([
      {
        plugin_id: "agent_team",
        key: "SELECTED_TEAM_ID",
        effective: false,
        suppresses_core_persona_selector: true,
      },
    ])).toBe(false);
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

  expect(pluginOptionPathFromDeclaration(declarations[0])).toEqual({ pluginId: AGENT_TEAM_PLUGIN_ID, key: AGENT_TEAM_SELECTED_TEAM_OPTION });
  expect(firstEffectivePluginOptionPath(declarations, { effectiveOnly: true })).toEqual({ pluginId: "other_plugin", key: "SELECTED_ITEM_ID" });
});
