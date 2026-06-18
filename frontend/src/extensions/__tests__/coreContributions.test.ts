import assert from "node:assert/strict";
import test from "node:test";
import {
  APP_ROUTE_CONTRIBUTIONS,
  BUILTIN_PLUGIN_APP_ROUTES,
  BUILTIN_PLUGIN_CHANNEL_CONNECTORS,
  BUILTIN_PLUGIN_FILE_VIEWERS,
  BUILTIN_PLUGIN_I18N_NAMESPACES,
  BUILTIN_PLUGIN_MESSAGE_ACTIONS,
  BUILTIN_PLUGIN_SKILL_IMPORTERS,
  BUILTIN_PLUGIN_SIDEBAR_MORE_NAV,
  BUILTIN_PLUGIN_TOOL_RENDERERS,
  BUILTIN_PLUGIN_USER_MENU_ITEMS,
  CORE_APP_ROUTES,
  CORE_PANEL_CONTRIBUTIONS,
  CORE_SETTINGS_SECTIONS,
  CORE_SIDEBAR_MORE_NAV,
  CORE_TOOL_RENDERERS,
  CORE_USER_MENU_ITEMS,
  PANEL_CONTRIBUTIONS,
  USER_MENU_CONTRIBUTIONS,
  buildAppRouteContributions,
  buildChannelConnectorContributions,
  buildFileViewerContributions,
  buildI18nNamespaceContributions,
  buildMessageActionContributions,
  buildPanelContributions,
  buildPluginAssetSlotContributions,
  buildPluginContributionPreview,
  buildSidebarMoreNavContributions,
  buildSkillImporterContributions,
  buildToolRendererContributions,
  buildUserMenuContributions,
  FEEDBACK_FRONTEND_PLUGIN_CONTRIBUTIONS,
  findAppRouteContribution,
  findCoreAppRoute,
  findCorePanelContribution,
  findPanelContribution,
  getCoreToolRendererId,
  getToolRendererId,
  hasCoreToolRenderer,
  hasChannelConnectorContribution,
  hasFileViewerContribution,
  hasI18nNamespaceContribution,
  hasMessageActionContribution,
  hasPluginAssetSlotContribution,
  hasSkillImporterContribution,
  hasToolRenderer,
  type PluginRuntimeContributionState,
} from "../coreContributions";
import { Permission } from "../../types";
import type { TabType } from "../../components/layout/AppContent/types";

function enabledToolPlugin(
  pluginId: "image_generation" | "audio_transcription",
): PluginRuntimeContributionState {
  const isImage = pluginId === "image_generation";
  return {
    plugin_id: pluginId,
    enabled: true,
    executable: true,
    status: "enabled",
    tools: [
      {
        name: isImage ? "image_generate" : "audio_transcribe",
        legacy_ids: [isImage ? "image_generate" : "audio_transcribe"],
      },
    ],
    frontend: {
      tool_renderers: [
        isImage
          ? "image_generation:image-generate"
          : "audio_transcription:audio-transcribe",
      ],
    },
  };
}

function enabledAdvancedFileViewersPlugin(): PluginRuntimeContributionState {
  return {
    plugin_id: "advanced_file_viewers",
    enabled: true,
    executable: true,
    status: "enabled",
    frontend: {
      file_viewers: [
        "advanced_file_viewers:pdf",
        "advanced_file_viewers:ppt",
        "advanced_file_viewers:word",
        "advanced_file_viewers:excel",
        "advanced_file_viewers:cad",
        "advanced_file_viewers:excalidraw",
        "advanced_file_viewers:html",
        "advanced_file_viewers:markdown",
        "advanced_file_viewers:code",
      ],
      i18n_namespaces: ["advanced_file_viewers:documents"],
    },
  };
}

function disabledPlugin(plugin: PluginRuntimeContributionState): PluginRuntimeContributionState {
  return {
    ...plugin,
    enabled: false,
    executable: false,
    status: "disabled",
  };
}

function enabledGithubInstallerPlugin(): PluginRuntimeContributionState {
  return {
    plugin_id: "github_installer",
    enabled: true,
    executable: true,
    status: "enabled",
    frontend: {
      skill_importers: ["github_installer:github-import"],
      i18n_namespaces: ["github_installer:skills"],
    },
  };
}

function enabledFeishuConnectorPlugin(): PluginRuntimeContributionState {
  return {
    plugin_id: "feishu_connector",
    enabled: true,
    executable: true,
    status: "enabled",
    frontend: {
      channel_connectors: ["feishu_connector:feishu"],
      i18n_namespaces: ["feishu_connector:channels"],
    },
  };
}

function enabledFeedbackPlugin(): PluginRuntimeContributionState {
  return {
    plugin_id: "feedback",
    enabled: true,
    executable: true,
    status: "enabled",
    frontend: {
      routes: ["feedback-route"],
      panels: ["feedback-panel"],
      nav_items: ["feedback-nav"],
      message_actions: ["feedback:message-feedback"],
      i18n_namespaces: ["feedback"],
    },
  };
}

function enabledUsageReportsPlugin(): PluginRuntimeContributionState {
  return {
    plugin_id: "usage_reports",
    enabled: true,
    executable: true,
    status: "enabled",
    frontend: {
      routes: ["usage_reports:usage-route"],
      panels: ["usage_reports:usage-panel"],
      nav_items: ["usage_reports:usage-menu"],
      i18n_namespaces: ["usage_reports:usage"],
    },
  };
}

function enabledAgentTeamPlugin(): PluginRuntimeContributionState {
  return {
    plugin_id: "agent_team",
    enabled: true,
    executable: true,
    status: "enabled",
    tools: [
      {
        name: "agent_team.search_persona_presets",
        legacy_ids: ["search_persona_presets"],
      },
      {
        name: "agent_team.create_agent_team",
        legacy_ids: ["create_agent_team"],
      },
    ],
    frontend: {
      routes: ["agent_team:team-route"],
      panels: ["agent_team:team-panel"],
      nav_items: ["agent_team:team-nav"],
      tool_renderers: ["agent_team:agent-team"],
      i18n_namespaces: ["agent_team:team"],
    },
  };
}

test("core app routes preserve legacy paths, SEO paths, and permissions", () => {
  const routes = new Map(CORE_APP_ROUTES.map((route) => [route.id, route]));

  assert.deepEqual(
    CORE_APP_ROUTES.map((route) => route.id),
    [
      "skills",
      "marketplace",
      "plugins",
      "mcp",
      "users",
      "roles",
      "settings",
      "channels",
      "agents",
      "persona",
      "files",
      "notifications",
      "memory",
      "scheduled-tasks",
    ],
  );
  assert.equal(routes.get("channels")?.path, "/channels/:channelType?/:instanceId?");
  assert.equal(routes.get("channels")?.seoPath, "/channels");
  assert.deepEqual(routes.get("skills")?.permissions, [
    Permission.SKILL_READ,
    Permission.MARKETPLACE_READ,
  ]);
  assert.equal(routes.get("plugins")?.path, "/plugins");
  assert.deepEqual(routes.get("plugins")?.permissions, [Permission.MARKETPLACE_READ]);
  assert.equal(routes.get("team"), undefined);
  assert.equal(routes.get("files")?.permissions, undefined);
  assert.equal(routes.get("usage"), undefined);
  assert.equal(routes.has("feedback"), false);
});

test("built-in plugin app contributions preserve Feedback, AgentTeam, and Usage entries", () => {
  const appRoutes = new Map(APP_ROUTE_CONTRIBUTIONS.map((route) => [route.id, route]));
  const feedback = appRoutes.get("feedback");
  const team = appRoutes.get("team");
  const usage = appRoutes.get("usage");

  assert.deepEqual(BUILTIN_PLUGIN_APP_ROUTES.map((route) => route.id), [
    "feedback",
    "team",
    "usage",
  ]);
  assert.equal(
    BUILTIN_PLUGIN_APP_ROUTES[0],
    FEEDBACK_FRONTEND_PLUGIN_CONTRIBUTIONS.appRoutes[0],
  );
  assert.equal(feedback?.path, "/feedback");
  assert.equal(feedback?.tab, "feedback");
  assert.deepEqual(feedback?.permissions, [Permission.FEEDBACK_READ]);
  assert.equal(team?.pluginId, "agent_team");
  assert.equal(team?.path, "/team");
  assert.equal(team?.tab, "team");
  assert.deepEqual(team?.permissions, [Permission.TEAM_READ]);
  assert.equal(usage?.pluginId, "usage_reports");
  assert.equal(usage?.path, "/usage");
  assert.equal(usage?.tab, "usage");
  assert.equal(usage?.redirectTo, "/chat");
  assert.equal(usage?.showNoPermissionToast, true);
  assert.deepEqual(usage?.permissions, [Permission.USAGE_READ]);
  assert.deepEqual(
    APP_ROUTE_CONTRIBUTIONS.map((route) => route.id),
    [
      "skills",
      "marketplace",
      "plugins",
      "mcp",
      "users",
      "roles",
      "settings",
      "feedback",
      "channels",
      "agents",
      "team",
      "persona",
      "files",
      "notifications",
      "memory",
      "scheduled-tasks",
      "usage",
    ],
  );
});

test("core panel contributions mirror non-chat app tabs", () => {
  const routeTabs = CORE_APP_ROUTES.map((route) => route.tab);
  const panelTabs = CORE_PANEL_CONTRIBUTIONS.map((panel) => panel.tab);

  assert.deepEqual(panelTabs, routeTabs);
  assert.equal(findCoreAppRoute("chat"), undefined);
  assert.equal(findCorePanelContribution("chat"), undefined);
  for (const tab of routeTabs) {
    assert.equal(findCoreAppRoute(tab)?.tab, tab);
    assert.equal(findCorePanelContribution(tab)?.tab, tab);
  }
  assert.equal(findCoreAppRoute("feedback"), undefined);
  assert.equal(findCorePanelContribution("feedback"), undefined);
  assert.equal(findCoreAppRoute("team"), undefined);
  assert.equal(findCorePanelContribution("team"), undefined);
  assert.equal(findCoreAppRoute("usage"), undefined);
  assert.equal(findCorePanelContribution("usage"), undefined);
});

test("app panel contributions include built-in plugin panels", () => {
  const routeTabs = APP_ROUTE_CONTRIBUTIONS.map((route) => route.tab);
  const panelTabs = PANEL_CONTRIBUTIONS.map((panel) => panel.tab);

  assert.deepEqual(panelTabs, routeTabs);
  assert.equal(findAppRouteContribution("chat"), undefined);
  assert.equal(findPanelContribution("chat"), undefined);
  assert.equal(findAppRouteContribution("feedback")?.tab, "feedback");
  assert.equal(findPanelContribution("feedback")?.tab, "feedback");
  assert.equal(findAppRouteContribution("usage")?.tab, "usage");
  assert.equal(findPanelContribution("usage")?.tab, "usage");
});

test("sidebar more menu keeps legacy order and visibility requirements", () => {
  assert.deepEqual(
    CORE_SIDEBAR_MORE_NAV.map((item) => item.id),
    ["persona", "skills", "plugins", "mcp", "channels", "memory"],
  );
  assert.equal(CORE_SIDEBAR_MORE_NAV[0].path, "/persona");
  assert.equal(CORE_SIDEBAR_MORE_NAV[0].labelKey, "personaPresets.title");
  assert.deepEqual(BUILTIN_PLUGIN_SIDEBAR_MORE_NAV[0].requiredAnyPermissions, [
    Permission.TEAM_READ,
  ]);
  assert.equal(BUILTIN_PLUGIN_SIDEBAR_MORE_NAV[0].pluginId, "agent_team");
  assert.equal(
    CORE_SIDEBAR_MORE_NAV[CORE_SIDEBAR_MORE_NAV.length - 1].requiresSetting,
    "memory",
  );
});

test("AgentTeam sidebar route panel and nav follow plugin runtime state", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledAgentTeamPlugin(),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledAgentTeamPlugin()),
  ];

  assert.equal(
    buildAppRouteContributions(enabledRuntimePlugins).some((route) => route.id === "team"),
    true,
  );
  assert.equal(
    buildPanelContributions(enabledRuntimePlugins).some((panel) => panel.id === "team"),
    true,
  );
  assert.equal(
    buildSidebarMoreNavContributions(enabledRuntimePlugins).some((item) => item.id === "team"),
    true,
  );
  assert.equal(
    buildAppRouteContributions(disabledRuntimePlugins).some((route) => route.id === "team"),
    false,
  );
  assert.equal(
    buildPanelContributions(disabledRuntimePlugins).some((panel) => panel.id === "team"),
    false,
  );
  assert.equal(
    buildSidebarMoreNavContributions(disabledRuntimePlugins).some((item) => item.id === "team"),
    false,
  );
});

test("user menu contributions preserve groups and permission semantics", () => {
  assert.deepEqual(
    CORE_USER_MENU_ITEMS.map((item) => `${item.group}:${item.id}`),
    [
      "admin:users",
      "admin:roles",
      "admin:agents",
      "system:notifications",
      "system:settings",
    ],
  );
  assert.deepEqual(
    CORE_USER_MENU_ITEMS.find((item) => item.id === "users")
      ?.requiredAnyPermissions,
    [Permission.USER_READ, Permission.USER_WRITE],
  );
  assert.deepEqual(
    CORE_USER_MENU_ITEMS.find((item) => item.id === "agents")
      ?.requiredAnyPermissions,
    [Permission.AGENT_ADMIN, Permission.MODEL_ADMIN],
  );
  assert.equal(CORE_USER_MENU_ITEMS.some((item) => item.id === "feedback"), false);
  assert.equal(CORE_USER_MENU_ITEMS.some((item) => item.id === "usage"), false);
});

test("built-in plugin user menu contributions preserve Feedback and Usage placement", () => {
  assert.deepEqual(BUILTIN_PLUGIN_USER_MENU_ITEMS.map((item) => item.id), [
    "feedback",
    "usage",
  ]);
  assert.equal(
    BUILTIN_PLUGIN_USER_MENU_ITEMS[0],
    FEEDBACK_FRONTEND_PLUGIN_CONTRIBUTIONS.userMenuItems[0],
  );
  assert.deepEqual(
    USER_MENU_CONTRIBUTIONS.map((item) => `${item.group}:${item.id}`),
    [
      "admin:users",
      "admin:roles",
      "admin:agents",
      "system:feedback",
      "system:usage",
      "system:notifications",
      "system:settings",
    ],
  );
  assert.deepEqual(
    USER_MENU_CONTRIBUTIONS.find((item) => item.id === "feedback")
      ?.requiredAnyPermissions,
    [Permission.FEEDBACK_READ],
  );
  assert.equal(
    USER_MENU_CONTRIBUTIONS.find((item) => item.id === "usage")?.pluginId,
    "usage_reports",
  );
  assert.deepEqual(
    USER_MENU_CONTRIBUTIONS.find((item) => item.id === "usage")
      ?.requiredAnyPermissions,
    [Permission.USAGE_READ],
  );
});

test("runtime contribution filtering keeps built-in plugin routes when runtime state is unavailable", () => {
  assert.equal(
    buildAppRouteContributions().some((route) => route.id === "feedback"),
    true,
  );
  assert.equal(
    buildPanelContributions().some((panel) => panel.id === "feedback"),
    true,
  );
  assert.equal(
    buildUserMenuContributions().some((item) => item.id === "feedback"),
    true,
  );
  assert.equal(
    buildAppRouteContributions().some((route) => route.id === "usage"),
    true,
  );
  assert.equal(
    buildPanelContributions().some((panel) => panel.id === "usage"),
    true,
  );
  assert.equal(
    buildUserMenuContributions().some((item) => item.id === "usage"),
    true,
  );
});

test("runtime contribution filtering keeps enabled executable Feedback", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledFeedbackPlugin(),
  ];

  assert.equal(
    buildAppRouteContributions(runtimePlugins).some(
      (route) => route.id === "feedback",
    ),
    true,
  );
  assert.equal(
    buildPanelContributions(runtimePlugins).some(
      (panel) => panel.id === "feedback",
    ),
    true,
  );
  assert.equal(
    buildUserMenuContributions(runtimePlugins).some(
      (item) => item.id === "feedback",
    ),
    true,
  );
});

test("runtime contribution filtering hides disabled Usage Reports by plugin id", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledUsageReportsPlugin()),
  ];

  assert.equal(
    buildAppRouteContributions(runtimePlugins).some((route) => route.id === "usage"),
    false,
  );
  assert.equal(
    buildPanelContributions(runtimePlugins).some((panel) => panel.id === "usage"),
    false,
  );
  assert.equal(
    buildUserMenuContributions(runtimePlugins).some((item) => item.id === "usage"),
    false,
  );
});

test("runtime contribution filtering hides disabled or non-executable Feedback", () => {
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    { ...enabledFeedbackPlugin(), enabled: false, status: "disabled" },
  ];
  const blockedRuntimePlugins: PluginRuntimeContributionState[] = [
    { ...enabledFeedbackPlugin(), executable: false, status: "blocked" },
  ];

  for (const runtimePlugins of [disabledRuntimePlugins, blockedRuntimePlugins]) {
    assert.equal(
      buildAppRouteContributions(runtimePlugins).some(
        (route) => route.id === "feedback",
      ),
      false,
    );
    assert.equal(
      buildPanelContributions(runtimePlugins).some(
        (panel) => panel.id === "feedback",
      ),
      false,
    );
    assert.equal(
      buildUserMenuContributions(runtimePlugins).some(
        (item) => item.id === "feedback",
      ),
      false,
    );
  }
});

test("runtime contribution preview reports Feedback entries removed by disable simulation", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledFeedbackPlugin(),
  ];
  const preview = buildPluginContributionPreview("feedback", runtimePlugins);

  assert.equal(preview.current.appRoutes.includes("/feedback"), true);
  assert.equal(preview.current.panels.includes("feedback"), true);
  assert.equal(preview.current.userMenuItems.includes("/feedback"), true);
  assert.deepEqual(preview.removedWhenDisabled.appRoutes, ["/feedback"]);
  assert.deepEqual(preview.removedWhenDisabled.panels, ["feedback"]);
  assert.deepEqual(preview.removedWhenDisabled.userMenuItems, ["/feedback"]);
  assert.deepEqual(preview.removedWhenDisabled.toolRenderers, []);
  assert.deepEqual(preview.removedWhenDisabled.skillImporters, []);
  assert.deepEqual(preview.removedWhenDisabled.messageActions, [
    "feedback:message-feedback",
  ]);
  assert.equal(preview.simulatedDisabled.appRoutes.includes("/feedback"), false);
});

test("runtime route panel and user menu contributions require explicit frontend declarations", () => {
  const runtimePluginsWithoutFrontend: PluginRuntimeContributionState[] = [
    {
      plugin_id: "feedback",
      enabled: true,
      executable: true,
      status: "enabled",
    },
    {
      plugin_id: "usage_reports",
      enabled: true,
      executable: true,
      status: "enabled",
    },
  ];

  assert.equal(
    buildAppRouteContributions(runtimePluginsWithoutFrontend).some(
      (route) => route.id === "feedback" || route.id === "usage",
    ),
    false,
  );
  assert.equal(
    buildPanelContributions(runtimePluginsWithoutFrontend).some(
      (panel) => panel.id === "feedback" || panel.id === "usage",
    ),
    false,
  );
  assert.equal(
    buildUserMenuContributions(runtimePluginsWithoutFrontend).some(
      (item) => item.id === "feedback" || item.id === "usage",
    ),
    false,
  );
});

test("Feedback message action follows plugin runtime state", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    {
      plugin_id: "feedback",
      enabled: true,
      executable: true,
      status: "enabled",
      frontend: {
        message_actions: ["feedback:message-feedback"],
      },
    },
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    {
      plugin_id: "feedback",
      enabled: false,
      executable: false,
      status: "disabled",
    },
  ];
  const blockedRuntimePlugins: PluginRuntimeContributionState[] = [
    {
      plugin_id: "feedback",
      enabled: true,
      executable: false,
      status: "blocked",
    },
  ];

  assert.deepEqual(BUILTIN_PLUGIN_MESSAGE_ACTIONS.map((action) => action.id), [
    "feedback:message-feedback",
  ]);
  assert.equal(
    BUILTIN_PLUGIN_MESSAGE_ACTIONS[0],
    FEEDBACK_FRONTEND_PLUGIN_CONTRIBUTIONS.messageActions[0],
  );
  assert.equal(hasMessageActionContribution("feedback"), true);
  assert.equal(hasMessageActionContribution("feedback", enabledRuntimePlugins), true);
  assert.equal(hasMessageActionContribution("feedback", disabledRuntimePlugins), false);
  assert.equal(hasMessageActionContribution("feedback", blockedRuntimePlugins), false);
  assert.deepEqual(
    buildMessageActionContributions(enabledRuntimePlugins).map((action) => action.id),
    ["feedback:message-feedback"],
  );
  assert.deepEqual(
    buildMessageActionContributions(disabledRuntimePlugins).map((action) => action.id),
    [],
  );
});

test("runtime message action contributions require explicit frontend declarations", () => {
  const runtimePluginsWithoutFrontend: PluginRuntimeContributionState[] = [
    {
      plugin_id: "feedback",
      enabled: true,
      executable: true,
      status: "enabled",
    },
  ];

  assert.equal(
    hasMessageActionContribution("feedback", runtimePluginsWithoutFrontend),
    false,
  );
  assert.deepEqual(
    buildMessageActionContributions(runtimePluginsWithoutFrontend).map(
      (action) => action.id,
    ),
    [],
  );
});

test("runtime contribution preview reports Usage Reports entries removed by disable simulation", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledUsageReportsPlugin(),
  ];
  const preview = buildPluginContributionPreview("usage_reports", runtimePlugins);

  assert.equal(preview.current.appRoutes.includes("/usage"), true);
  assert.equal(preview.current.panels.includes("usage"), true);
  assert.equal(preview.current.userMenuItems.includes("/usage"), true);
  assert.deepEqual(preview.removedWhenDisabled.appRoutes, ["/usage"]);
  assert.deepEqual(preview.removedWhenDisabled.panels, ["usage"]);
  assert.deepEqual(preview.removedWhenDisabled.userMenuItems, ["/usage"]);
});

test("settings sections preserve the legacy category order", () => {
  assert.deepEqual(
    CORE_SETTINGS_SECTIONS.map((section) => section.category),
    [
      "frontend",
      "agent",
      "llm",
      "session",
      "mongodb",
      "redis",
      "checkpoint",
      "long_term_storage",
      "memory",
      "memory_embedding",
      "memory_search",
      "memory_storage",
      "security",
      "email",
      "captcha",
      "s3",
      "file_upload",
      "sandbox",
      "skills",
      "tools",
      "audio_transcription",
      "tracing",
      "user",
      "oauth",
    ],
  );
});

test("core tool renderer contributions map current dedicated tool cards", () => {
  const toolNames = CORE_TOOL_RENDERERS.flatMap((renderer) => renderer.toolNames);

  assert.deepEqual(getCoreToolRendererId("scheduled_task_create"), "scheduled-task");
  assert.deepEqual(getCoreToolRendererId("env_var_delete"), "env-var");
  assert.equal(getCoreToolRendererId("create_agent_team"), undefined);
  assert.deepEqual(getCoreToolRendererId("memory_delete"), "memory-store");
  assert.equal(getCoreToolRendererId("image_generate"), undefined);
  assert.equal(getCoreToolRendererId("audio_transcribe"), undefined);
  assert.equal(hasCoreToolRenderer("ask_human"), true);
  assert.equal(hasCoreToolRenderer("image_generate"), false);
  assert.equal(hasCoreToolRenderer("audio_transcribe"), false);
  assert.equal(hasCoreToolRenderer("create_agent_team"), false);
  assert.equal(hasCoreToolRenderer("unknown_tool"), false);
  assert.ok(toolNames.includes("read_file"));
  assert.ok(toolNames.includes("search_tools"));
});

test("built-in plugin tool renderers follow plugin runtime state", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledAgentTeamPlugin(),
    enabledToolPlugin("image_generation"),
    enabledToolPlugin("audio_transcription"),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledAgentTeamPlugin()),
    disabledPlugin(enabledToolPlugin("image_generation")),
    disabledPlugin(enabledToolPlugin("audio_transcription")),
  ];

  assert.deepEqual(BUILTIN_PLUGIN_TOOL_RENDERERS.map((renderer) => renderer.id), [
    "agent-team",
    "image-generate",
    "audio-transcribe",
  ]);
  assert.equal(getToolRendererId("create_agent_team"), "agent-team");
  assert.equal(getToolRendererId("image_generate"), "image-generate");
  assert.equal(getToolRendererId("audio_transcribe"), "audio-transcribe");
  assert.equal(
    getToolRendererId("create_agent_team", enabledRuntimePlugins),
    "agent-team",
  );
  assert.equal(
    getToolRendererId("image_generate", enabledRuntimePlugins),
    "image-generate",
  );
  assert.equal(
    getToolRendererId("audio_transcribe", enabledRuntimePlugins),
    "audio-transcribe",
  );
  assert.equal(getToolRendererId("create_agent_team", disabledRuntimePlugins), undefined);
  assert.equal(getToolRendererId("image_generate", disabledRuntimePlugins), undefined);
  assert.equal(getToolRendererId("audio_transcribe", disabledRuntimePlugins), undefined);
  assert.equal(hasToolRenderer("image_generate", enabledRuntimePlugins), true);
  assert.equal(hasToolRenderer("audio_transcribe", enabledRuntimePlugins), true);
  assert.equal(hasToolRenderer("create_agent_team", enabledRuntimePlugins), true);
  assert.equal(hasToolRenderer("create_agent_team", disabledRuntimePlugins), false);
  assert.equal(hasToolRenderer("image_generate", disabledRuntimePlugins), false);
  assert.equal(hasToolRenderer("audio_transcribe", disabledRuntimePlugins), false);
  assert.deepEqual(
    buildToolRendererContributions(disabledRuntimePlugins).map(
      (renderer) => renderer.id,
    ),
    CORE_TOOL_RENDERERS.map((renderer) => renderer.id),
  );
});

test("runtime contribution preview reports plugin tool renderers removed by disable", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledToolPlugin("image_generation"),
  ];
  const preview = buildPluginContributionPreview("image_generation", runtimePlugins);

  assert.equal(preview.current.toolRenderers.includes("image-generate"), true);
  assert.deepEqual(preview.removedWhenDisabled.toolRenderers, ["image-generate"]);
  assert.equal(preview.simulatedDisabled.toolRenderers.includes("image-generate"), false);
});

test("runtime contribution preview reports audio transcription renderer removed by disable", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledToolPlugin("audio_transcription"),
  ];
  const preview = buildPluginContributionPreview("audio_transcription", runtimePlugins);

  assert.equal(preview.current.toolRenderers.includes("audio-transcribe"), true);
  assert.deepEqual(preview.removedWhenDisabled.toolRenderers, ["audio-transcribe"]);
  assert.equal(preview.simulatedDisabled.toolRenderers.includes("audio-transcribe"), false);
});

test("advanced file viewers follow plugin runtime state", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledAdvancedFileViewersPlugin(),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledAdvancedFileViewersPlugin()),
  ];

  assert.deepEqual(BUILTIN_PLUGIN_FILE_VIEWERS.map((viewer) => viewer.id), [
    "pdf",
    "ppt",
    "word",
    "excel",
    "cad",
    "excalidraw",
    "html",
    "markdown",
    "code",
  ]);
  assert.equal(hasFileViewerContribution("pdf"), true);
  assert.equal(hasFileViewerContribution("pdf", enabledRuntimePlugins), true);
  assert.equal(hasFileViewerContribution("pdf", disabledRuntimePlugins), false);
  assert.deepEqual(
    buildFileViewerContributions(disabledRuntimePlugins).map((viewer) => viewer.id),
    [],
  );
});

test("runtime contribution preview reports advanced file viewers removed by disable", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledAdvancedFileViewersPlugin(),
  ];
  const preview = buildPluginContributionPreview(
    "advanced_file_viewers",
    runtimePlugins,
  );

  assert.equal(preview.current.fileViewers.includes("pdf"), true);
  assert.deepEqual(preview.removedWhenDisabled.fileViewers, [
    "pdf",
    "ppt",
    "word",
    "excel",
    "cad",
    "excalidraw",
    "html",
    "markdown",
    "code",
  ]);
  assert.equal(preview.simulatedDisabled.fileViewers.includes("pdf"), false);
});

test("runtime frontend contributions require explicit manifest declarations", () => {
  const runtimePluginsWithoutFrontend: PluginRuntimeContributionState[] = [
    {
      plugin_id: "image_generation",
      enabled: true,
      executable: true,
      status: "enabled",
      tools: [{ name: "image_generate", legacy_ids: ["image_generate"] }],
    },
    {
      plugin_id: "advanced_file_viewers",
      enabled: true,
      executable: true,
      status: "enabled",
    },
    {
      plugin_id: "github_installer",
      enabled: true,
      executable: true,
      status: "enabled",
    },
    {
      plugin_id: "feishu_connector",
      enabled: true,
      executable: true,
      status: "enabled",
    },
  ];

  assert.equal(getToolRendererId("image_generate", runtimePluginsWithoutFrontend), undefined);
  assert.equal(hasFileViewerContribution("pdf", runtimePluginsWithoutFrontend), false);
  assert.equal(
    buildToolRendererContributions(runtimePluginsWithoutFrontend).some(
      (renderer) => renderer.id === "image-generate",
    ),
    false,
  );
  assert.deepEqual(buildFileViewerContributions(runtimePluginsWithoutFrontend), []);
  assert.deepEqual(buildSkillImporterContributions(runtimePluginsWithoutFrontend), []);
  assert.deepEqual(buildChannelConnectorContributions(runtimePluginsWithoutFrontend), []);
  assert.deepEqual(buildI18nNamespaceContributions(runtimePluginsWithoutFrontend), []);
});

test("plugin i18n namespaces follow runtime frontend metadata", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledAdvancedFileViewersPlugin(),
    enabledGithubInstallerPlugin(),
    enabledFeishuConnectorPlugin(),
  ];
  const disabledRuntimePlugins = runtimePlugins.map(disabledPlugin);

  assert.deepEqual(BUILTIN_PLUGIN_I18N_NAMESPACES.map((item) => item.id), [
    "advanced_file_viewers:documents",
    "github_installer:skills",
    "feishu_connector:channels",
  ]);
  assert.equal(hasI18nNamespaceContribution("advanced_file_viewers:documents"), true);
  assert.equal(
    hasI18nNamespaceContribution("advanced_file_viewers:documents", runtimePlugins),
    true,
  );
  assert.equal(
    hasI18nNamespaceContribution("advanced_file_viewers:documents", disabledRuntimePlugins),
    false,
  );
  assert.deepEqual(
    buildI18nNamespaceContributions(runtimePlugins).map((item) => item.id),
    [
      "advanced_file_viewers:documents",
      "github_installer:skills",
      "feishu_connector:channels",
    ],
  );
  assert.deepEqual(buildI18nNamespaceContributions(disabledRuntimePlugins), []);
});

test("runtime contribution preview reports i18n namespaces removed by disable", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledAdvancedFileViewersPlugin(),
  ];

  const preview = buildPluginContributionPreview(
    "advanced_file_viewers",
    runtimePlugins,
  );

  assert.deepEqual(preview.current.i18nNamespaces, [
    "advanced_file_viewers:documents",
  ]);
  assert.deepEqual(preview.removedWhenDisabled.i18nNamespaces, [
    "advanced_file_viewers:documents",
  ]);
  assert.deepEqual(preview.simulatedDisabled.i18nNamespaces, []);
});

test("frontend asset slot contributions come from runtime package metadata", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    {
      plugin_id: "advanced_file_viewers",
      enabled: true,
      executable: true,
      status: "enabled",
      package: {
        frontend_assets: {
          plugin_id: "advanced_file_viewers",
          asset_schema: "lambchat.plugin.frontend-assets.v1",
          slots: ["file_viewer"],
          assets: ["widget.js"],
          phase: "static_asset_mount_placeholder",
        },
      },
    },
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    {
      ...enabledRuntimePlugins[0],
      enabled: false,
      executable: false,
      status: "disabled",
    },
  ];
  const mismatchedRuntimePlugins: PluginRuntimeContributionState[] = [
    {
      ...enabledRuntimePlugins[0],
      package: {
        frontend_assets: {
          plugin_id: "other_plugin",
          asset_schema: "lambchat.plugin.frontend-assets.v1",
          slots: ["file_viewer"],
          assets: ["widget.js"],
          phase: "static_asset_mount_placeholder",
        },
      },
    },
  ];

  const contributions = buildPluginAssetSlotContributions(enabledRuntimePlugins);

  assert.equal(hasPluginAssetSlotContribution("file_viewer", enabledRuntimePlugins), true);
  assert.equal(hasPluginAssetSlotContribution("file_viewer", disabledRuntimePlugins), false);
  assert.deepEqual(
    contributions.map((contribution) => ({
      id: contribution.id,
      pluginId: contribution.pluginId,
      slot: contribution.slot,
      assetSchema: contribution.assetSchema,
      assets: contribution.assets,
      mountPath: contribution.mountPath,
      area: contribution.area,
    })),
    [
      {
        id: "advanced_file_viewers:file_viewer",
        pluginId: "advanced_file_viewers",
        slot: "file_viewer",
        assetSchema: "lambchat.plugin.frontend-assets.v1",
        assets: ["widget.js"],
        mountPath: "/plugin-assets/advanced_file_viewers/",
        area: "plugin_asset_slot",
      },
    ],
  );
  assert.deepEqual(buildPluginAssetSlotContributions(disabledRuntimePlugins), []);
  assert.deepEqual(buildPluginAssetSlotContributions(mismatchedRuntimePlugins), []);
});

test("runtime contribution preview reports frontend asset slots removed by disable", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    {
      plugin_id: "advanced_file_viewers",
      enabled: true,
      executable: true,
      status: "enabled",
      package: {
        frontend_assets: {
          plugin_id: "advanced_file_viewers",
          asset_schema: "lambchat.plugin.frontend-assets.v1",
          slots: ["file_viewer"],
          assets: [],
          phase: "static_asset_mount_placeholder",
        },
      },
    },
  ];

  const preview = buildPluginContributionPreview(
    "advanced_file_viewers",
    runtimePlugins,
  );

  assert.deepEqual(preview.current.pluginAssetSlots, [
    "advanced_file_viewers:file_viewer",
  ]);
  assert.deepEqual(preview.removedWhenDisabled.pluginAssetSlots, [
    "advanced_file_viewers:file_viewer",
  ]);
  assert.deepEqual(preview.simulatedDisabled.pluginAssetSlots, []);
});

test("GitHub skill importer follows plugin runtime state", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledGithubInstallerPlugin(),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledGithubInstallerPlugin()),
  ];

  assert.deepEqual(BUILTIN_PLUGIN_SKILL_IMPORTERS.map((importer) => importer.id), [
    "github-import",
  ]);
  assert.equal(hasSkillImporterContribution("github-import"), true);
  assert.equal(
    hasSkillImporterContribution("github-import", enabledRuntimePlugins),
    true,
  );
  assert.equal(
    hasSkillImporterContribution("github-import", disabledRuntimePlugins),
    false,
  );
  assert.deepEqual(
    buildSkillImporterContributions(disabledRuntimePlugins).map(
      (importer) => importer.id,
    ),
    [],
  );
});

test("Feishu channel connector follows plugin runtime state", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledFeishuConnectorPlugin(),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledFeishuConnectorPlugin()),
  ];

  assert.deepEqual(BUILTIN_PLUGIN_CHANNEL_CONNECTORS.map((connector) => connector.id), [
    "feishu_connector:feishu",
  ]);
  assert.equal(hasChannelConnectorContribution("feishu"), true);
  assert.equal(
    hasChannelConnectorContribution("feishu", enabledRuntimePlugins),
    true,
  );
  assert.equal(
    hasChannelConnectorContribution("feishu", disabledRuntimePlugins),
    false,
  );
  assert.deepEqual(
    buildChannelConnectorContributions(disabledRuntimePlugins).map(
      (connector) => connector.id,
    ),
    [],
  );
});

test("runtime contribution preview reports Feishu connector removed by disable", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledFeishuConnectorPlugin(),
  ];
  const preview = buildPluginContributionPreview("feishu_connector", runtimePlugins);

  assert.equal(preview.current.channelConnectors.includes("feishu_connector:feishu"), true);
  assert.deepEqual(preview.removedWhenDisabled.channelConnectors, [
    "feishu_connector:feishu",
  ]);
  assert.equal(
    preview.simulatedDisabled.channelConnectors.includes("feishu_connector:feishu"),
    false,
  );
});

test("runtime contribution preview reports GitHub skill importer removed by disable", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledGithubInstallerPlugin(),
  ];
  const preview = buildPluginContributionPreview("github_installer", runtimePlugins);

  assert.equal(preview.current.skillImporters.includes("github-import"), true);
  assert.deepEqual(preview.removedWhenDisabled.skillImporters, ["github-import"]);
  assert.equal(
    preview.simulatedDisabled.skillImporters.includes("github-import"),
    false,
  );
});

test("core route ids remain valid non-chat tab values", () => {
  const tabs: readonly TabType[] = APP_ROUTE_CONTRIBUTIONS.map((route) => route.tab);

  assert.equal(tabs.includes("chat"), false);
  assert.equal(new Set(tabs).size, tabs.length);
});
