import assert from "node:assert/strict";
import test from "node:test";
import {
  APP_ROUTE_CONTRIBUTIONS,
  CORE_APP_ROUTES,
  CORE_PANEL_CONTRIBUTIONS,
  CORE_SETTINGS_SECTIONS,
  CORE_SIDEBAR_MORE_NAV,
  CORE_TOOL_RENDERERS,
  CORE_USER_MENU_ITEMS,
  PANEL_CONTRIBUTIONS,
  USER_MENU_CONTRIBUTIONS,
  buildAppRouteContributions,
  buildAgentCatalogEntryContributions,
  buildAgentCategoryContributions,
  buildAssistantIdentityResolverContributions,
  buildChannelOptionContributions,
  buildChannelConnectorContributions,
  buildChatInputOptionContributions,
  buildChatInputPanelContributions,
  buildFileViewerContributions,
  buildI18nNamespaceContributions,
  buildMentionProviderContributions,
  buildMessageActionContributions,
  buildPanelContributions,
  buildPluginAssetSlotContributions,
  buildPluginContributionPreview,
  buildProjectOptionContributions,
  buildScheduledTaskOptionContributions,
  buildSidebarMoreNavContributions,
  buildSessionOptionContributions,
  buildSkillImporterContributions,
  buildToolRendererContributions,
  buildUploadHandlerContributions,
  buildUserMenuContributions,
  buildWelcomeSurfaceContributions,
  findAgentCatalogEntryContribution,
  findAssistantIdentityResolverContribution,
  findAppRouteContribution,
  findChannelConnectorContribution,
  findCoreAppRoute,
  findCorePanelContribution,
  findPanelContribution,
  getCoreToolRendererId,
  getToolRendererId,
  hasCoreToolRenderer,
  hasAgentCatalogEntryContribution,
  hasChannelConnectorContribution,
  hasFileViewerContribution,
  hasI18nNamespaceContribution,
  hasMessageActionContribution,
  hasPluginAssetSlotContribution,
  hasRuntimeManagedChannelConnector,
  hasSkillImporterContribution,
  hasToolRenderer,
  isRuntimePluginExecutable,
  isRuntimePluginExecutableById,
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
          ? {
              id: "image_generation:image-generate",
              tool_names: ["image_generation.image_generate", "image_generate"],
            }
          : {
              id: "audio_transcription:audio-transcribe",
              tool_names: ["audio_transcription.audio_transcribe", "audio_transcribe"],
            },
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
        { id: "advanced_file_viewers:pdf", extensions: ["pdf"] },
        { id: "advanced_file_viewers:ppt", extensions: ["ppt", "pptx"] },
        { id: "advanced_file_viewers:word", extensions: ["docx"] },
        { id: "advanced_file_viewers:excel", extensions: ["xls", "xlsx", "csv"] },
        { id: "advanced_file_viewers:cad", extensions: ["dxf", "dwg"] },
        { id: "advanced_file_viewers:excalidraw", extensions: ["excalidraw"] },
        { id: "advanced_file_viewers:html", extensions: ["html", "htm"] },
        { id: "advanced_file_viewers:markdown", extensions: ["md", "markdown"] },
        { id: "advanced_file_viewers:code", extensions: ["*"] },
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
      skill_importers: [
        { id: "github_installer:github-import", source: "github" },
      ],
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
      channel_connectors: [
        {
          id: "feishu_connector:feishu",
          channel_type: "feishu",
          panel_renderer: "feishu_connector.FeishuPanel",
        },
      ],
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
      app_tabs: [
        {
          id: "feedback:feedback-tab",
          tab: "feedback",
          path: "/feedback",
          label: "nav.feedback",
          panel: "feedback:feedback-panel",
          insert_after: "settings",
          order: 610,
          permissions: [Permission.FEEDBACK_READ],
          seo_title: "seo.feedback.title",
          seo_description: "seo.feedback.description",
          redirect_to: "/chat",
          show_no_permission_toast: true,
        },
      ],
      app_panels: [
        {
          id: "feedback:feedback-panel",
          tab: "feedback",
          renderer: "feedback.FeedbackPanel",
        },
      ],
      user_menu_items: [
        {
          id: "feedback:feedback-nav",
          path: "/feedback",
          label: "nav.feedback",
          icon: "Star",
          group: "system",
          order: 50,
          permissions: [Permission.FEEDBACK_READ],
        },
      ],
      message_actions: [
        {
          id: "feedback:message-feedback",
          target: "assistant_message",
          renderer: "feedback.FeedbackButtons",
          order: 20,
          permissions: [Permission.FEEDBACK_WRITE],
        },
      ],
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
      app_tabs: [
        {
          id: "usage_reports:usage-tab",
          tab: "usage",
          path: "/usage",
          label: "nav.usage",
          panel: "usage_reports:usage-panel",
          insert_after: "scheduled-tasks",
          order: 620,
          permissions: [Permission.USAGE_READ],
          seo_title: "seo.usage.title",
          seo_description: "seo.usage.description",
          redirect_to: "/chat",
          show_no_permission_toast: true,
        },
      ],
      app_panels: [
        {
          id: "usage_reports:usage-panel",
          tab: "usage",
          renderer: "usage_reports.UsagePanel",
        },
      ],
      user_menu_items: [
        {
          id: "usage_reports:usage-menu",
          path: "/usage",
          label: "nav.usage",
          icon: "BarChart3",
          group: "system",
          order: 60,
          permissions: [Permission.USAGE_READ],
        },
      ],
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
    agents: [
      {
        id: "team",
        module: "src.agents.team_agent.graph.TeamAgent",
        name: "agents.team.name",
        description: "agents.team.description",
        icon: "Users",
        sort_order: 15,
        category: "agent_team:team-builder",
        required_permissions: [Permission.TEAM_READ],
      },
    ],
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
      app_tabs: [
        {
          id: "agent_team:agent-team-tab",
          tab: "agent-team",
          path: "/agent-team",
          label: "nav.team",
          panel: "agent_team:agent-team-panel",
          insert_after: "agents",
          order: 420,
          permissions: [Permission.TEAM_READ],
          seo_title: "seo.team.title",
          seo_description: "seo.team.description",
        },
      ],
      app_panels: [
        {
          id: "agent_team:agent-team-panel",
          tab: "agent-team",
          renderer: "agent_team.TeamBuilderPanel",
        },
      ],
      sidebar_items: [
        {
          id: "agent_team:agent-team-nav",
          path: "/agent-team",
          label: "nav.team",
          icon: "Users",
          order: 20,
          permissions: [Permission.TEAM_READ],
        },
      ],
      tool_renderers: [
        {
          id: "agent_team:agent-team",
          tool_names: [
            "agent_team.search_persona_presets",
            "agent_team.create_agent_team",
            "search_persona_presets",
            "create_agent_team",
          ],
        },
      ],
      chat_input_options: [
        {
          id: "agent_team:select-team",
          slot: "enhance",
          label: "featureMenu.team",
          icon: "UsersRound",
          panel: "agent_team:team-picker",
          selected_renderer: "agent_team.SelectedTeamChip",
          suppresses_core_persona_selector: true,
          shortcut: "mod+t",
          order: 20,
          option_binding: {
            plugin_id: "agent_team",
            key: "SELECTED_TEAM_ID",
            scope: "session",
          },
          visible_when: { agent_id: "team" },
        },
      ],
      chat_input_panels: [
        {
          id: "agent_team:team-picker",
          renderer: "agent_team.TeamPickerModal",
          create_path: "/agent-team",
          manage_path: "/agent-team",
          option_binding: {
            plugin_id: "agent_team",
            key: "SELECTED_TEAM_ID",
            scope: "session",
          },
          visible_when: { agent_id: "team" },
        },
      ],
      mention_providers: [
        {
          id: "agent_team:team-mentions",
          trigger: "@",
          mode: "team",
          provider: "agent_team.searchTeams",
          visible_when: { agent_id: "team" },
        },
      ],
      welcome_surfaces: [
        {
          id: "agent_team:team-welcome",
          agent_id: "team",
          renderer: "agent_team.TeamWelcomeSurface",
          order: 20,
          visible_when: { agent_id: "team" },
        },
      ],
      assistant_identity_resolvers: [
        {
          id: "agent_team:team-assistant-identity",
          agent_id: "team",
          resolver: "agent_team.TeamAssistantIdentity",
          order: 20,
          visible_when: { agent_id: "team" },
        },
      ],
      agent_categories: [
        {
          id: "agent_team:team-builder",
          label: "agentTeam.category.teamBuilder",
          description: "Agent Team owned team-building agents.",
          icon: "Users",
          order: 20,
        },
      ],
      project_options: [
        {
          key: "DEFAULT_TEAM_ID",
          type: "string",
          label: "agentTeam.settings.defaultTeam",
          description: "Default Agent Team selected for this project.",
          group: "project",
          order: 10,
        },
      ],
      session_options: [
        {
          key: "SELECTED_TEAM_ID",
          type: "string",
          label: "agentTeam.session.selectedTeam",
          description: "Agent Team selected for the current chat session.",
          group: "session",
          order: 10,
          visible_when: { agent_id: "team" },
        },
      ],
      channel_options: [
        {
          key: "SELECTED_TEAM_ID",
          type: "string",
          label: "agentTeam.channel.selectedTeam",
          description: "Agent Team selected for plugin-owned channel runs.",
          group: "channel",
          order: 10,
          visible_when: { route: "/channels/feishu" },
        },
      ],
      scheduled_task_options: [
        {
          key: "SELECTED_TEAM_ID",
          type: "string",
          label: "agentTeam.scheduledTask.selectedTeam",
          description: "Agent Team selected for plugin-owned scheduled task runs.",
          group: "scheduled_task",
          order: 10,
          visible_when: { agent_id: "team" },
        },
      ],
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

test("default route snapshot is core-only and plugin pages require runtime declarations", () => {
  const appRoutes = new Map(APP_ROUTE_CONTRIBUTIONS.map((route) => [route.id, route]));
  const runtimeRoutes = new Map(
    buildAppRouteContributions([
      enabledFeedbackPlugin(),
      enabledAgentTeamPlugin(),
      enabledUsageReportsPlugin(),
    ]).map((route) => [route.id, route]),
  );

  assert.equal(appRoutes.get("feedback"), undefined);
  assert.equal(appRoutes.get("team"), undefined);
  assert.equal(appRoutes.get("usage"), undefined);
  assert.equal(runtimeRoutes.get("feedback")?.path, "/feedback");
  assert.deepEqual(runtimeRoutes.get("feedback")?.permissions, [
    Permission.FEEDBACK_READ,
  ]);
  const team = runtimeRoutes.get("agent-team");
  assert.equal(team?.pluginId, "agent_team");
  assert.equal(team?.path, "/agent-team");
  assert.equal(team?.tab, "agent-team");
  assert.equal(team?.insertAfterId, "agents");
  assert.deepEqual(team?.permissions, [Permission.TEAM_READ]);
  const usage = runtimeRoutes.get("usage");
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
      "channels",
      "agents",
      "persona",
      "files",
      "notifications",
      "memory",
      "scheduled-tasks",
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

test("default panel contributions mirror core routes and exclude plugin panels", () => {
  const routeTabs = APP_ROUTE_CONTRIBUTIONS.map((route) => route.tab);
  const panelTabs = PANEL_CONTRIBUTIONS.map((panel) => panel.tab);

  assert.deepEqual(panelTabs, routeTabs);
  assert.equal(findAppRouteContribution("chat"), undefined);
  assert.equal(findPanelContribution("chat"), undefined);
  assert.equal(findAppRouteContribution("feedback"), undefined);
  assert.equal(findPanelContribution("feedback"), undefined);
  assert.equal(findAppRouteContribution("team"), undefined);
  assert.equal(findPanelContribution("team"), undefined);
  assert.equal(findAppRouteContribution("usage"), undefined);
  assert.equal(findPanelContribution("usage"), undefined);
});

test("structured plugin app tab and panel declarations drive runtime routes", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledFeedbackPlugin(),
    enabledAgentTeamPlugin(),
    enabledUsageReportsPlugin(),
  ];

  const routes = new Map(buildAppRouteContributions(runtimePlugins).map((route) => [route.id, route]));
  const panels = new Map(buildPanelContributions(runtimePlugins).map((panel) => [panel.id, panel]));

  assert.equal(routes.get("feedback")?.path, "/feedback");
  assert.equal(routes.get("feedback")?.insertAfterId, "settings");
  assert.equal(findAppRouteContribution("feedback", runtimePlugins)?.path, "/feedback");
  assert.equal(panels.get("feedback")?.renderer, "feedback.FeedbackPanel");
  assert.equal(findPanelContribution("feedback", runtimePlugins)?.renderer, "feedback.FeedbackPanel");
  assert.equal(routes.get("agent-team")?.path, "/agent-team");
  assert.equal(routes.get("agent-team")?.insertAfterId, "agents");
  assert.equal(findAppRouteContribution("agent-team", runtimePlugins)?.path, "/agent-team");
  assert.equal(panels.get("agent-team")?.renderer, "agent_team.TeamBuilderPanel");
  assert.equal(findPanelContribution("agent-team", runtimePlugins)?.renderer, "agent_team.TeamBuilderPanel");
  assert.equal(routes.get("usage")?.path, "/usage");
  assert.equal(routes.get("usage")?.insertAfterId, "scheduled-tasks");
  assert.equal(findAppRouteContribution("usage", runtimePlugins)?.path, "/usage");
  assert.equal(panels.get("usage")?.renderer, "usage_reports.UsagePanel");
  assert.equal(findPanelContribution("usage", runtimePlugins)?.renderer, "usage_reports.UsagePanel");
});

test("runtime route and panel lookup respects disabled plugin state", () => {
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledFeedbackPlugin()),
    disabledPlugin(enabledAgentTeamPlugin()),
  ];

  assert.equal(findAppRouteContribution("feedback", disabledRuntimePlugins), undefined);
  assert.equal(findPanelContribution("feedback", disabledRuntimePlugins), undefined);
  assert.equal(findAppRouteContribution("team", disabledRuntimePlugins), undefined);
  assert.equal(findPanelContribution("team", disabledRuntimePlugins), undefined);
});

test("structured plugin declarations do not require legacy route panel or nav ids", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledFeedbackPlugin(),
    enabledAgentTeamPlugin(),
    enabledUsageReportsPlugin(),
  ];

  assert.deepEqual(
    runtimePlugins.map((plugin) => ({
      pluginId: plugin.plugin_id,
      routes: plugin.frontend?.routes ?? [],
      panels: plugin.frontend?.panels ?? [],
      navItems: plugin.frontend?.nav_items ?? [],
    })),
    [
      { pluginId: "feedback", routes: [], panels: [], navItems: [] },
      { pluginId: "agent_team", routes: [], panels: [], navItems: [] },
      { pluginId: "usage_reports", routes: [], panels: [], navItems: [] },
    ],
  );
  assert.deepEqual(
    buildAppRouteContributions(runtimePlugins)
      .filter((route) => ["feedback", "agent-team", "usage"].includes(route.id))
      .map((route) => `${route.id}:${route.path}`),
    ["feedback:/feedback", "agent-team:/agent-team", "usage:/usage"],
  );
  assert.deepEqual(
    buildPanelContributions(runtimePlugins)
      .filter((panel) => ["feedback", "agent-team", "usage"].includes(panel.id))
      .map((panel) => `${panel.id}:${panel.renderer}`),
    [
      "feedback:feedback.FeedbackPanel",
      "agent-team:agent_team.TeamBuilderPanel",
      "usage:usage_reports.UsagePanel",
    ],
  );
});

test("legacy route panel and nav ids no longer synthesize runtime plugin UI", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    {
      plugin_id: "feedback",
      enabled: true,
      executable: true,
      status: "enabled",
      frontend: {
        routes: ["feedback-route"],
        panels: ["feedback-panel"],
        nav_items: ["feedback-nav"],
      },
    },
    {
      plugin_id: "agent_team",
      enabled: true,
      executable: true,
      status: "enabled",
      frontend: {
        routes: ["agent_team:team-route"],
        panels: ["agent_team:agent-team-panel"],
        nav_items: ["agent_team:agent-team-nav"],
      },
    },
    {
      plugin_id: "usage_reports",
      enabled: true,
      executable: true,
      status: "enabled",
      frontend: {
        routes: ["usage_reports:usage-route"],
        panels: ["usage_reports:usage-panel"],
        nav_items: ["usage_reports:usage-menu"],
      },
    },
  ];

  assert.equal(
    buildAppRouteContributions(runtimePlugins).some((route) =>
      ["feedback", "team", "usage"].includes(route.id),
    ),
    false,
  );
  assert.equal(
    buildPanelContributions(runtimePlugins).some((panel) =>
      ["feedback", "team", "usage"].includes(panel.id),
    ),
    false,
  );
  assert.equal(
    buildUserMenuContributions(runtimePlugins).some((item) =>
      ["feedback", "usage"].includes(item.id),
    ),
    false,
  );
  assert.equal(
    buildSidebarMoreNavContributions(runtimePlugins).some((item) => item.id === "team"),
    false,
  );
});

test("runtime app tab declarations can add new plugin-owned pages", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    {
      plugin_id: "review_center",
      enabled: true,
      executable: true,
      status: "enabled",
      frontend: {
        app_tabs: [
          {
            id: "review_center:reviews-tab",
            tab: "reviews",
            path: "/reviews",
            label: "reviewCenter.nav",
            panel: "review_center:reviews-panel",
            insert_after: "plugins",
            order: 300,
            permissions: [Permission.MARKETPLACE_READ],
            seo_title: "seo.reviews.title",
            seo_description: "seo.reviews.description",
          },
        ],
        app_panels: [
          {
            id: "review_center:reviews-panel",
            tab: "reviews",
            renderer: "review_center.ReviewsPanel",
          },
        ],
        sidebar_items: [
          {
            id: "review_center:reviews-nav",
            path: "/reviews",
            label: "reviewCenter.nav",
            icon: "Star",
            order: 30,
            permissions: [Permission.MARKETPLACE_READ],
          },
        ],
        user_menu_items: [
          {
            id: "review_center:reviews-menu",
            path: "/reviews",
            label: "reviewCenter.nav",
            icon: "Star",
            group: "system",
            order: 70,
            permissions: [Permission.MARKETPLACE_READ],
          },
        ],
      },
    },
  ];

  assert.equal(
    buildAppRouteContributions(runtimePlugins).find((route) => route.id === "reviews")?.path,
    "/reviews",
  );
  assert.equal(
    buildPanelContributions(runtimePlugins).find((panel) => panel.id === "reviews")?.renderer,
    "review_center.ReviewsPanel",
  );
  assert.equal(
    buildSidebarMoreNavContributions(runtimePlugins).find((item) => item.path === "/reviews")?.pluginId,
    "review_center",
  );
  assert.equal(
    buildUserMenuContributions(runtimePlugins).find((item) => item.path === "/reviews")?.pluginId,
    "review_center",
  );
});

test("runtime app tab declarations cannot replace the core chat tab", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    {
      plugin_id: "bad_chat_plugin",
      enabled: true,
      executable: true,
      status: "enabled",
      frontend: {
        app_tabs: [
          {
            id: "bad_chat_plugin:chat-tab",
            tab: "chat",
            path: "/plugin-chat",
            label: "bad.chat",
            panel: "bad_chat_plugin:chat-panel",
            order: 10,
          },
        ],
        app_panels: [
          {
            id: "bad_chat_plugin:chat-panel",
            tab: "chat",
            renderer: "bad_chat_plugin.ChatPanel",
          },
        ],
      },
    },
  ];

  assert.equal(
    buildAppRouteContributions(runtimePlugins).some((route) => route.path === "/plugin-chat"),
    false,
  );
  assert.equal(
    buildPanelContributions(runtimePlugins).some(
      (panel) => panel.renderer === "bad_chat_plugin.ChatPanel",
    ),
    false,
  );
});

test("sidebar more menu keeps legacy order and visibility requirements", () => {
  assert.deepEqual(
    CORE_SIDEBAR_MORE_NAV.map((item) => item.id),
    ["persona", "skills", "plugins", "mcp", "channels", "memory"],
  );
  assert.equal(CORE_SIDEBAR_MORE_NAV[0].path, "/persona");
  assert.equal(CORE_SIDEBAR_MORE_NAV[0].labelKey, "personaPresets.title");
  assert.equal(CORE_SIDEBAR_MORE_NAV.some((item) => item.id === "team"), false);
  const runtimeTeamItem = buildSidebarMoreNavContributions([
    enabledAgentTeamPlugin(),
  ]).find((item) => item.id === "team");
  assert.deepEqual(runtimeTeamItem?.requiredAnyPermissions, [Permission.TEAM_READ]);
  assert.equal(runtimeTeamItem?.pluginId, "agent_team");
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
    buildSidebarMoreNavContributions(enabledRuntimePlugins).find((item) => item.id === "team")
      ?.labelKey,
    "nav.team",
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

test("AgentTeam chat input and mention contributions follow runtime state and agent context", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledAgentTeamPlugin(),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledAgentTeamPlugin()),
  ];

  assert.deepEqual(
    buildChatInputOptionContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (option) => `${option.id}:${option.optionBinding?.pluginId}.${option.optionBinding?.key}:${option.selectedRenderer}:${option.suppressesCorePersonaSelector}:${option.shortcut}`,
    ),
    ["agent_team:select-team:agent_team.SELECTED_TEAM_ID:agent_team.SelectedTeamChip:true:mod+t"],
  );
  assert.deepEqual(
    buildChatInputPanelContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (panel) => `${panel.id}:${panel.optionBinding?.pluginId}.${panel.optionBinding?.key}:${panel.renderer}:${panel.createPath}:${panel.managePath}`,
    ),
    ["agent_team:team-picker:agent_team.SELECTED_TEAM_ID:agent_team.TeamPickerModal:/agent-team:/agent-team"],
  );
  assert.deepEqual(
    buildMentionProviderContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (provider) => `${provider.id}:${provider.provider}`,
    ),
    ["agent_team:team-mentions:agent_team.searchTeams"],
  );
  assert.deepEqual(
    buildWelcomeSurfaceContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (surface) => `${surface.id}:${surface.renderer}`,
    ),
    ["agent_team:team-welcome:agent_team.TeamWelcomeSurface"],
  );
  assert.deepEqual(
    buildAssistantIdentityResolverContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (resolver) => `${resolver.id}:${resolver.resolver}`,
    ),
    ["agent_team:team-assistant-identity:agent_team.TeamAssistantIdentity"],
  );
  assert.equal(
    findAssistantIdentityResolverContribution(
      "agent_team.TeamAssistantIdentity",
      enabledRuntimePlugins,
      { agentId: "team" },
    )?.pluginId,
    "agent_team",
  );
  assert.deepEqual(
    buildAgentCatalogEntryContributions(enabledRuntimePlugins).map(
      (entry) => `${entry.id}:${entry.pluginId}:${entry.sortOrder}`,
    ),
    ["team:agent_team:15"],
  );
  assert.equal(
    findAgentCatalogEntryContribution("team", enabledRuntimePlugins)?.pluginId,
    "agent_team",
  );
  assert.equal(hasAgentCatalogEntryContribution("team", enabledRuntimePlugins), true);
  assert.equal(hasAgentCatalogEntryContribution("team", disabledRuntimePlugins), false);
  assert.deepEqual(buildAgentCatalogEntryContributions(disabledRuntimePlugins), []);
  assert.deepEqual(
    buildPluginContributionPreview("agent_team", enabledRuntimePlugins)
      .removedWhenDisabled.agentCatalogEntries,
    ["team"],
  );
  assert.deepEqual(
    buildPluginContributionPreview("agent_team", enabledRuntimePlugins)
      .removedWhenDisabled.assistantIdentityResolvers,
    ["agent_team:team-assistant-identity"],
  );
  const agentTeamDisablePreview = buildPluginContributionPreview(
    "agent_team",
    enabledRuntimePlugins,
  );
  const agentTeamDisablePreviewForTeamAgent = buildPluginContributionPreview(
    "agent_team",
    enabledRuntimePlugins,
    { agentId: "team" },
  );
  const agentTeamDisablePreviewForFeishuChannel = buildPluginContributionPreview(
    "agent_team",
    enabledRuntimePlugins,
    { route: "/channels/feishu" },
  );
  assert.deepEqual(agentTeamDisablePreview.removedWhenDisabled.projectOptions, [
    "agent_team.DEFAULT_TEAM_ID",
  ]);
  assert.deepEqual(agentTeamDisablePreviewForTeamAgent.removedWhenDisabled.sessionOptions, [
    "agent_team.SELECTED_TEAM_ID",
  ]);
  assert.deepEqual(agentTeamDisablePreviewForFeishuChannel.removedWhenDisabled.channelOptions, [
    "agent_team.SELECTED_TEAM_ID",
  ]);
  assert.deepEqual(agentTeamDisablePreviewForTeamAgent.removedWhenDisabled.scheduledTaskOptions, [
    "agent_team.SELECTED_TEAM_ID",
  ]);
  assert.deepEqual(
    buildAgentCategoryContributions(enabledRuntimePlugins).map(
      (category) => `${category.id}:${category.label}`,
    ),
    ["agent_team:team-builder:agentTeam.category.teamBuilder"],
  );
  assert.deepEqual(
    buildAgentCatalogEntryContributions(enabledRuntimePlugins).map(
      (agent) => `${agent.id}:${agent.category}`,
    ),
    ["team:agent_team:team-builder"],
  );
  assert.deepEqual(
    buildProjectOptionContributions(enabledRuntimePlugins).map((option) => option.id),
    ["agent_team.DEFAULT_TEAM_ID"],
  );
  assert.deepEqual(
    buildSessionOptionContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (option) => option.id,
    ),
    ["agent_team.SELECTED_TEAM_ID"],
  );
  assert.deepEqual(
    buildChannelOptionContributions(enabledRuntimePlugins, { route: "/channels/feishu" }).map(
      (option) => `${option.id}:${option.area}`,
    ),
    ["agent_team.SELECTED_TEAM_ID:channel_option"],
  );
  assert.deepEqual(
    buildScheduledTaskOptionContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (option) => `${option.id}:${option.area}`,
    ),
    ["agent_team.SELECTED_TEAM_ID:scheduled_task_option"],
  );
  assert.deepEqual(
    buildChatInputOptionContributions(enabledRuntimePlugins, { agentId: "default" }),
    [],
  );
  assert.deepEqual(
    buildSessionOptionContributions(enabledRuntimePlugins, { agentId: "default" }),
    [],
  );
  assert.deepEqual(
    buildChannelOptionContributions(enabledRuntimePlugins, { route: "/channels/slack" }),
    [],
  );
  assert.deepEqual(
    buildWelcomeSurfaceContributions(enabledRuntimePlugins, { agentId: "default" }),
    [],
  );
  assert.deepEqual(
    buildScheduledTaskOptionContributions(enabledRuntimePlugins, { agentId: "default" }),
    [],
  );
  assert.deepEqual(buildChatInputOptionContributions(disabledRuntimePlugins, { agentId: "team" }), []);
  assert.deepEqual(buildChatInputPanelContributions(disabledRuntimePlugins, { agentId: "team" }), []);
  assert.deepEqual(buildMentionProviderContributions(disabledRuntimePlugins, { agentId: "team" }), []);
  assert.deepEqual(buildWelcomeSurfaceContributions(disabledRuntimePlugins, { agentId: "team" }), []);
  assert.deepEqual(buildAgentCategoryContributions(disabledRuntimePlugins), []);
  assert.deepEqual(buildProjectOptionContributions(disabledRuntimePlugins), []);
  assert.deepEqual(buildChannelOptionContributions(disabledRuntimePlugins, { route: "/channels/feishu" }), []);
  assert.deepEqual(buildScheduledTaskOptionContributions(disabledRuntimePlugins, { agentId: "team" }), []);
  assert.deepEqual(
    buildProjectOptionContributions(disabledRuntimePlugins, undefined, { includeInactive: true }).map(
      (option) => `${option.id}:${option.effective}:${option.pluginStatus}`,
    ),
    ["agent_team.DEFAULT_TEAM_ID:false:disabled"],
  );
  assert.deepEqual(buildSessionOptionContributions(disabledRuntimePlugins, { agentId: "team" }), []);
  assert.deepEqual(
    buildChannelOptionContributions(
      disabledRuntimePlugins,
      { route: "/channels/feishu" },
      { includeInactive: true },
    ).map((option) => `${option.id}:${option.effective}:${option.pluginStatus}`),
    ["agent_team.SELECTED_TEAM_ID:false:disabled"],
  );
  assert.deepEqual(
    buildScheduledTaskOptionContributions(
      disabledRuntimePlugins,
      { agentId: "team" },
      { includeInactive: true },
    ).map((option) => `${option.id}:${option.effective}:${option.pluginStatus}`),
    ["agent_team.SELECTED_TEAM_ID:false:disabled"],
  );
});

test("runtime plugin executability helpers centralize enabled and executable state", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledAgentTeamPlugin(),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledAgentTeamPlugin()),
  ];

  assert.equal(isRuntimePluginExecutable(enabledRuntimePlugins[0]), true);
  assert.equal(
    isRuntimePluginExecutableById(enabledRuntimePlugins, "agent_team"),
    true,
  );
  assert.equal(
    isRuntimePluginExecutableById(disabledRuntimePlugins, "agent_team"),
    false,
  );
  assert.equal(isRuntimePluginExecutableById(undefined, "agent_team"), false);
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

test("default user menu is core-only and plugin menu items require runtime declarations", () => {
  assert.deepEqual(
    USER_MENU_CONTRIBUTIONS.map((item) => `${item.group}:${item.id}`),
    [
      "admin:users",
      "admin:roles",
      "admin:agents",
      "system:notifications",
      "system:settings",
    ],
  );
  assert.equal(USER_MENU_CONTRIBUTIONS.some((item) => item.id === "feedback"), false);
  assert.equal(USER_MENU_CONTRIBUTIONS.some((item) => item.id === "usage"), false);
  const runtimeMenuItems = buildUserMenuContributions([
    enabledFeedbackPlugin(),
    enabledUsageReportsPlugin(),
  ]);
  assert.deepEqual(
    runtimeMenuItems.find((item) => item.id === "feedback")?.requiredAnyPermissions,
    [Permission.FEEDBACK_READ],
  );
  assert.equal(
    runtimeMenuItems.find((item) => item.id === "usage")?.pluginId,
    "usage_reports",
  );
  assert.deepEqual(
    runtimeMenuItems.find((item) => item.id === "usage")?.requiredAnyPermissions,
    [Permission.USAGE_READ],
  );
});

test("runtime contribution builders fail closed for plugin UI when runtime state is unavailable", () => {
  assert.equal(
    buildAppRouteContributions().some((route) => route.id === "team"),
    false,
  );
  assert.equal(
    buildPanelContributions().some((panel) => panel.id === "team"),
    false,
  );
  assert.equal(
    buildSidebarMoreNavContributions().some((item) => item.id === "team"),
    false,
  );
  assert.equal(
    buildAgentCategoryContributions().some(
      (category) => category.id === "agent_team:team-builder",
    ),
    false,
  );
  assert.equal(
    buildAgentCatalogEntryContributions().some((entry) => entry.id === "team"),
    false,
  );
  assert.equal(
    buildAppRouteContributions().some((route) => route.id === "feedback"),
    false,
  );
  assert.equal(
    buildPanelContributions().some((panel) => panel.id === "feedback"),
    false,
  );
  assert.equal(
    buildUserMenuContributions().some((item) => item.id === "feedback"),
    false,
  );
  assert.equal(
    buildAppRouteContributions().some((route) => route.id === "usage"),
    false,
  );
  assert.equal(
    buildPanelContributions().some((panel) => panel.id === "usage"),
    false,
  );
  assert.equal(
    buildUserMenuContributions().some((item) => item.id === "usage"),
    false,
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
        message_actions: [
          {
            id: "feedback:message-feedback",
            target: "assistant_message",
            renderer: "feedback.FeedbackButtons",
            order: 20,
            permissions: [Permission.FEEDBACK_WRITE],
          },
        ],
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

  assert.equal(hasMessageActionContribution("feedback"), false);
  assert.equal(hasMessageActionContribution("feedback", enabledRuntimePlugins), true);
  assert.equal(hasMessageActionContribution("feedback", disabledRuntimePlugins), false);
  assert.equal(hasMessageActionContribution("feedback", blockedRuntimePlugins), false);
  assert.deepEqual(
    buildMessageActionContributions(enabledRuntimePlugins).map(
      (action) => `${action.id}:${action.target}:${action.renderer}:${action.order}`,
    ),
    ["feedback:message-feedback:assistant_message:feedback.FeedbackButtons:20"],
  );
  assert.deepEqual(
    buildMessageActionContributions(enabledRuntimePlugins, {
      target: "assistant_message",
    }).map((action) => action.id),
    ["feedback:message-feedback"],
  );
  assert.deepEqual(
    buildMessageActionContributions(enabledRuntimePlugins, {
      target: "user_message",
    }).map((action) => action.id),
    [],
  );
  assert.deepEqual(
    buildMessageActionContributions(disabledRuntimePlugins).map((action) => action.id),
    [],
  );
});

test("message action target context isolates plugin-declared message slots", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    {
      plugin_id: "workflow_runner",
      enabled: true,
      executable: true,
      status: "enabled",
      frontend: {
        message_actions: [
          {
            id: "workflow_runner:retry-user-message",
            target: "user_message",
            renderer: "workflow_runner.RetryUserMessage",
            order: 30,
          },
          {
            id: "workflow_runner:inspect-tool-result",
            target: "tool_result",
            renderer: "workflow_runner.InspectToolResult",
            order: 20,
          },
        ],
      },
    },
  ];

  assert.deepEqual(
    buildMessageActionContributions(runtimePlugins, {
      target: "assistant_message",
    }),
    [],
  );
  assert.deepEqual(
    buildMessageActionContributions(runtimePlugins, { target: "user_message" }).map(
      (action) => action.id,
    ),
    ["workflow_runner:retry-user-message"],
  );
  assert.deepEqual(
    buildMessageActionContributions(runtimePlugins, { target: "tool_result" }).map(
      (action) => action.id,
    ),
    ["workflow_runner:inspect-tool-result"],
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
  const runtimePluginsWithLegacyString: PluginRuntimeContributionState[] = [
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
  assert.equal(
    hasMessageActionContribution("feedback", runtimePluginsWithLegacyString),
    false,
  );
  assert.deepEqual(buildMessageActionContributions(runtimePluginsWithLegacyString), []);
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
      "tracing",
      "user",
      "oauth",
    ],
  );
  assert.equal(
    CORE_SETTINGS_SECTIONS.some(
      (section) => (section.category as string) === "audio_transcription",
    ),
    false,
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

test("plugin tool renderers follow plugin runtime state", () => {
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

  assert.equal(getToolRendererId("create_agent_team"), undefined);
  assert.equal(getToolRendererId("image_generate"), undefined);
  assert.equal(getToolRendererId("audio_transcribe"), undefined);
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

  assert.deepEqual(buildFileViewerContributions(enabledRuntimePlugins).map((viewer) => viewer.id), [
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
  assert.equal(hasFileViewerContribution("pdf"), false);
  assert.equal(hasFileViewerContribution("pdf", enabledRuntimePlugins), true);
  assert.equal(hasFileViewerContribution("pdf", disabledRuntimePlugins), false);
  assert.deepEqual(
    buildFileViewerContributions(disabledRuntimePlugins).map((viewer) => viewer.id),
    [],
  );
});

test("upload handler declarations are metadata-only runtime contributions", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    {
      plugin_id: "upload_demo",
      enabled: true,
      executable: true,
      status: "enabled",
      frontend: {
        upload_handlers: [
          {
            id: "upload_demo:markdown-import",
            accept: [".md", "text/markdown"],
            max_bytes: 1048576,
            handler: "upload_demo.markdownImport",
          },
        ],
      },
    },
  ];

  assert.deepEqual(buildUploadHandlerContributions(runtimePlugins), [
    {
      id: "upload_demo:markdown-import",
      pluginId: "upload_demo",
      accept: [".md", "text/markdown"],
      maxBytes: 1048576,
      handler: "upload_demo.markdownImport",
      area: "upload_handler",
    },
  ]);
  assert.deepEqual(buildUploadHandlerContributions([disabledPlugin(runtimePlugins[0])]), []);
});

test("integration contributions can carry plugin-declared structured metadata", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    {
      plugin_id: "image_generation",
      enabled: true,
      executable: true,
      status: "enabled",
      frontend: {
        tool_renderers: [
          {
            id: "image_generation:custom-image-card",
            tool_names: ["image_generation.custom_image"],
          },
        ],
      },
    },
    {
      plugin_id: "advanced_file_viewers",
      enabled: true,
      executable: true,
      status: "enabled",
      frontend: {
        file_viewers: [
          { id: "advanced_file_viewers:diagram", extensions: ["drawio"] },
        ],
      },
    },
    {
      plugin_id: "github_installer",
      enabled: true,
      executable: true,
      status: "enabled",
      frontend: {
        skill_importers: [
          { id: "github_installer:zip-import", source: "zip" },
        ],
      },
    },
    {
      plugin_id: "feishu_connector",
      enabled: true,
      executable: true,
      status: "enabled",
      frontend: {
        channel_connectors: [
          {
            id: "feishu_connector:tenant",
            channel_type: "feishu-tenant",
            panel_renderer: "feishu_connector.TenantPanel",
          },
        ],
      },
    },
  ];

  assert.deepEqual(buildToolRendererContributions(runtimePlugins).at(-1), {
    id: "custom-image-card",
    toolNames: ["image_generation.custom_image"],
    area: "tool_renderer",
  });
  assert.deepEqual(buildFileViewerContributions(runtimePlugins), [
    { id: "diagram", extensions: ["drawio"], area: "file_viewer" },
  ]);
  assert.deepEqual(buildSkillImporterContributions(runtimePlugins), [
    { id: "zip-import", source: "zip", area: "skill_importer" },
  ]);
  assert.deepEqual(buildChannelConnectorContributions(runtimePlugins), [
    {
      id: "feishu_connector:tenant",
      pluginId: "feishu_connector",
      channelType: "feishu-tenant",
      panelRenderer: "feishu_connector.TenantPanel",
      area: "channel_connector",
    },
  ]);
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

test("runtime integration contributions require structured metadata", () => {
  const runtimePluginsWithLegacyStrings: PluginRuntimeContributionState[] = [
    enabledToolPlugin("image_generation"),
    enabledAdvancedFileViewersPlugin(),
    enabledGithubInstallerPlugin(),
    enabledFeishuConnectorPlugin(),
  ].map((plugin) => ({
    ...plugin,
    frontend: {
      ...plugin.frontend,
      tool_renderers: ["image_generation:image-generate"],
      file_viewers: ["advanced_file_viewers:pdf"],
      skill_importers: ["github_installer:github-import"],
      channel_connectors: ["feishu_connector:feishu"],
    },
  }));

  assert.deepEqual(
    buildToolRendererContributions(runtimePluginsWithLegacyStrings),
    CORE_TOOL_RENDERERS,
  );
  assert.deepEqual(buildFileViewerContributions(runtimePluginsWithLegacyStrings), []);
  assert.deepEqual(buildSkillImporterContributions(runtimePluginsWithLegacyStrings), []);
  assert.deepEqual(buildChannelConnectorContributions(runtimePluginsWithLegacyStrings), []);
});

test("plugin i18n namespaces follow runtime frontend metadata", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledAdvancedFileViewersPlugin(),
    enabledGithubInstallerPlugin(),
    enabledFeishuConnectorPlugin(),
  ];
  const disabledRuntimePlugins = runtimePlugins.map(disabledPlugin);

  assert.equal(hasI18nNamespaceContribution("advanced_file_viewers:documents"), false);
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

  assert.deepEqual(buildSkillImporterContributions(enabledRuntimePlugins).map((importer) => importer.id), [
    "github-import",
  ]);
  assert.equal(hasSkillImporterContribution("github-import"), false);
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

  assert.deepEqual(buildChannelConnectorContributions(enabledRuntimePlugins).map((connector) => connector.id), [
    "feishu_connector:feishu",
  ]);
  assert.equal(
    findChannelConnectorContribution("feishu", enabledRuntimePlugins)?.panelRenderer,
    "feishu_connector.FeishuPanel",
  );
  assert.equal(hasChannelConnectorContribution("feishu"), false);
  assert.equal(hasRuntimeManagedChannelConnector("feishu"), false);
  assert.equal(
    hasRuntimeManagedChannelConnector("feishu", enabledRuntimePlugins),
    true,
  );
  assert.equal(
    hasRuntimeManagedChannelConnector("feishu", disabledRuntimePlugins),
    true,
  );
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

test("core contribution module does not keep static built-in plugin UI fallback tables", async () => {
  const { readFileSync } = await import("node:fs");
  const source = readFileSync(
    new URL("../coreContributions.ts", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(source, /BUILTIN_PLUGIN_/);
  assert.match(source, /plugin\.frontend\?\.app_tabs/);
  assert.match(source, /plugin\.frontend\?\.tool_renderers/);
  assert.match(source, /plugin\.frontend\?\.file_viewers/);
  assert.match(source, /plugin\.frontend\?\.message_actions/);
});
