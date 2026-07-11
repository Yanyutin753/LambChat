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
  buildPluginMessageRendererContributions,
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
  getPluginMessageRenderer,
  getToolRendererId,
  hasCoreToolRenderer,
  hasAgentCatalogEntryContribution,
  hasChannelConnectorContribution,
  hasFileViewerContribution,
  hasI18nNamespaceContribution,
  hasMessageActionContribution,
  hasPluginMessageRenderer,
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
        module: "./backend/runtime/graph.py:TeamAgent",
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

  expect(CORE_APP_ROUTES.map((route) => route.id)).toEqual([
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
    ]);
  expect(routes.get("channels")?.path).toBe("/channels/:channelType?/:instanceId?");
  expect(routes.get("channels")?.seoPath).toBe("/channels");
  expect(routes.get("skills")?.permissions).toEqual([
    Permission.SKILL_READ,
    Permission.MARKETPLACE_READ,
  ]);
  expect(routes.get("plugins")?.path).toBe("/plugins");
  expect(routes.get("plugins")?.permissions).toEqual([Permission.MARKETPLACE_READ]);
  expect(routes.get("team")).toBe(undefined);
  expect(routes.get("files")?.permissions).toBe(undefined);
  expect(routes.get("usage")).toBe(undefined);
  expect(routes.has("feedback")).toBe(false);
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

  expect(appRoutes.get("feedback")).toBe(undefined);
  expect(appRoutes.get("team")).toBe(undefined);
  expect(appRoutes.get("usage")).toBe(undefined);
  expect(runtimeRoutes.get("feedback")?.path).toBe("/feedback");
  expect(runtimeRoutes.get("feedback")?.permissions).toEqual([
    Permission.FEEDBACK_READ,
  ]);
  const team = runtimeRoutes.get("agent-team");
  expect(team?.pluginId).toBe("agent_team");
  expect(team?.path).toBe("/agent-team");
  expect(team?.tab).toBe("agent-team");
  expect(team?.insertAfterId).toBe("agents");
  expect(team?.permissions).toEqual([Permission.TEAM_READ]);
  const usage = runtimeRoutes.get("usage");
  expect(usage?.pluginId).toBe("usage_reports");
  expect(usage?.path).toBe("/usage");
  expect(usage?.tab).toBe("usage");
  expect(usage?.redirectTo).toBe("/chat");
  expect(usage?.showNoPermissionToast).toBe(true);
  expect(usage?.permissions).toEqual([Permission.USAGE_READ]);
  expect(APP_ROUTE_CONTRIBUTIONS.map((route) => route.id)).toEqual([
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
    ]);
});

test("core panel contributions mirror non-chat app tabs", () => {
  const routeTabs = CORE_APP_ROUTES.map((route) => route.tab);
  const panelTabs = CORE_PANEL_CONTRIBUTIONS.map((panel) => panel.tab);

  expect(panelTabs).toEqual(routeTabs);
  expect(findCoreAppRoute("chat")).toBe(undefined);
  expect(findCorePanelContribution("chat")).toBe(undefined);
  for (const tab of routeTabs) {
    expect(findCoreAppRoute(tab)?.tab).toBe(tab);
    expect(findCorePanelContribution(tab)?.tab).toBe(tab);
  }
  expect(findCoreAppRoute("feedback")).toBe(undefined);
  expect(findCorePanelContribution("feedback")).toBe(undefined);
  expect(findCoreAppRoute("team")).toBe(undefined);
  expect(findCorePanelContribution("team")).toBe(undefined);
  expect(findCoreAppRoute("usage")).toBe(undefined);
  expect(findCorePanelContribution("usage")).toBe(undefined);
});

test("default panel contributions mirror core routes and exclude plugin panels", () => {
  const routeTabs = APP_ROUTE_CONTRIBUTIONS.map((route) => route.tab);
  const panelTabs = PANEL_CONTRIBUTIONS.map((panel) => panel.tab);

  expect(panelTabs).toEqual(routeTabs);
  expect(findAppRouteContribution("chat")).toBe(undefined);
  expect(findPanelContribution("chat")).toBe(undefined);
  expect(findAppRouteContribution("feedback")).toBe(undefined);
  expect(findPanelContribution("feedback")).toBe(undefined);
  expect(findAppRouteContribution("team")).toBe(undefined);
  expect(findPanelContribution("team")).toBe(undefined);
  expect(findAppRouteContribution("usage")).toBe(undefined);
  expect(findPanelContribution("usage")).toBe(undefined);
});

test("structured plugin app tab and panel declarations drive runtime routes", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledFeedbackPlugin(),
    enabledAgentTeamPlugin(),
    enabledUsageReportsPlugin(),
  ];

  const routes = new Map(buildAppRouteContributions(runtimePlugins).map((route) => [route.id, route]));
  const panels = new Map(buildPanelContributions(runtimePlugins).map((panel) => [panel.id, panel]));

  expect(routes.get("feedback")?.path).toBe("/feedback");
  expect(routes.get("feedback")?.insertAfterId).toBe("settings");
  expect(findAppRouteContribution("feedback", runtimePlugins)?.path).toBe("/feedback");
  expect(panels.get("feedback")?.renderer).toBe("feedback.FeedbackPanel");
  expect(findPanelContribution("feedback", runtimePlugins)?.renderer).toBe("feedback.FeedbackPanel");
  expect(routes.get("agent-team")?.path).toBe("/agent-team");
  expect(routes.get("agent-team")?.insertAfterId).toBe("agents");
  expect(findAppRouteContribution("agent-team", runtimePlugins)?.path).toBe("/agent-team");
  expect(panels.get("agent-team")?.renderer).toBe("agent_team.TeamBuilderPanel");
  expect(findPanelContribution("agent-team", runtimePlugins)?.renderer).toBe("agent_team.TeamBuilderPanel");
  expect(routes.get("usage")?.path).toBe("/usage");
  expect(routes.get("usage")?.insertAfterId).toBe("scheduled-tasks");
  expect(findAppRouteContribution("usage", runtimePlugins)?.path).toBe("/usage");
  expect(panels.get("usage")?.renderer).toBe("usage_reports.UsagePanel");
  expect(findPanelContribution("usage", runtimePlugins)?.renderer).toBe("usage_reports.UsagePanel");
});

test("runtime route and panel lookup respects disabled plugin state", () => {
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledFeedbackPlugin()),
    disabledPlugin(enabledAgentTeamPlugin()),
  ];

  expect(findAppRouteContribution("feedback", disabledRuntimePlugins)).toBe(undefined);
  expect(findPanelContribution("feedback", disabledRuntimePlugins)).toBe(undefined);
  expect(findAppRouteContribution("team", disabledRuntimePlugins)).toBe(undefined);
  expect(findPanelContribution("team", disabledRuntimePlugins)).toBe(undefined);
});

test("structured plugin declarations do not require legacy route panel or nav ids", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledFeedbackPlugin(),
    enabledAgentTeamPlugin(),
    enabledUsageReportsPlugin(),
  ];

  expect(runtimePlugins.map((plugin) => ({
      pluginId: plugin.plugin_id,
      routes: plugin.frontend?.routes ?? [],
      panels: plugin.frontend?.panels ?? [],
      navItems: plugin.frontend?.nav_items ?? [],
    }))).toEqual([
      { pluginId: "feedback", routes: [], panels: [], navItems: [] },
      { pluginId: "agent_team", routes: [], panels: [], navItems: [] },
      { pluginId: "usage_reports", routes: [], panels: [], navItems: [] },
    ]);
  expect(buildAppRouteContributions(runtimePlugins)
      .filter((route) => ["feedback", "agent-team", "usage"].includes(route.id))
      .map((route) => `${route.id}:${route.path}`)).toEqual(["feedback:/feedback", "agent-team:/agent-team", "usage:/usage"]);
  expect(buildPanelContributions(runtimePlugins)
      .filter((panel) => ["feedback", "agent-team", "usage"].includes(panel.id))
      .map((panel) => `${panel.id}:${panel.renderer}`)).toEqual([
      "feedback:feedback.FeedbackPanel",
      "agent-team:agent_team.TeamBuilderPanel",
      "usage:usage_reports.UsagePanel",
    ]);
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

  expect(buildAppRouteContributions(runtimePlugins).some((route) =>
      ["feedback", "team", "usage"].includes(route.id),
    )).toBe(false);
  expect(buildPanelContributions(runtimePlugins).some((panel) =>
      ["feedback", "team", "usage"].includes(panel.id),
    )).toBe(false);
  expect(buildUserMenuContributions(runtimePlugins).some((item) =>
      ["feedback", "usage"].includes(item.id),
    )).toBe(false);
  expect(buildSidebarMoreNavContributions(runtimePlugins).some((item) => item.id === "team")).toBe(false);
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

  expect(buildAppRouteContributions(runtimePlugins).find((route) => route.id === "reviews")?.path).toBe("/reviews");
  expect(buildPanelContributions(runtimePlugins).find((panel) => panel.id === "reviews")?.renderer).toBe("review_center.ReviewsPanel");
  expect(buildSidebarMoreNavContributions(runtimePlugins).find((item) => item.path === "/reviews")?.pluginId).toBe("review_center");
  expect(buildUserMenuContributions(runtimePlugins).find((item) => item.path === "/reviews")?.pluginId).toBe("review_center");
});

test("runtime app tab declarations can insert after another plugin route", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledAgentTeamPlugin(),
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
            label: "nav.reviews",
            panel: "review_center:reviews-panel",
            insert_after: "agent-team",
            order: 430,
          },
          {
            id: "review_center:review-detail-tab",
            tab: "review-detail",
            path: "/reviews/:reviewId",
            label: "nav.reviewDetail",
            panel: "review_center:review-detail-panel",
            insert_after: "reviews",
            order: 431,
          },
        ],
        app_panels: [
          {
            id: "review_center:reviews-panel",
            tab: "reviews",
            renderer: "review_center.ReviewsPanel",
          },
          {
            id: "review_center:review-detail-panel",
            tab: "review-detail",
            renderer: "review_center.ReviewDetailPanel",
          },
        ],
        sidebar_items: [
          {
            id: "review_center:reviews-nav",
            path: "/reviews",
            label: "nav.reviews",
            icon: "Star",
            order: 30,
          },
        ],
      },
    },
  ];

  const routes = buildAppRouteContributions(runtimePlugins);
  const routeIds = routes.map((route) => route.id);

  expect(routes.find((route) => route.id === "reviews")?.path).toBe("/reviews");
  expect(routes.find((route) => route.id === "review-detail")?.path).toBe("/reviews/:reviewId");
  expect(routeIds.indexOf("reviews")).toBe(routeIds.indexOf("agent-team") + 1);
  expect(routeIds.indexOf("review-detail")).toBe(routeIds.indexOf("reviews") + 1);
  expect(buildPanelContributions(runtimePlugins).find((panel) => panel.id === "reviews")?.renderer).toBe("review_center.ReviewsPanel");
  expect(buildPanelContributions(runtimePlugins).find((panel) => panel.id === "review-detail")?.renderer).toBe("review_center.ReviewDetailPanel");
  const reviewsNav = buildSidebarMoreNavContributions(runtimePlugins).find(
    (item) => item.id === "reviews",
  );
  expect(reviewsNav?.path).toBe("/reviews");
  expect(reviewsNav?.labelKey).toBe("nav.reviews");
});

test("plugin route panel and nav follow plugin runtime state", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledAgentTeamPlugin(),
    enabledUsageReportsPlugin(),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledAgentTeamPlugin(),
    disabledPlugin(enabledUsageReportsPlugin()),
  ];

  expect(buildAppRouteContributions(enabledRuntimePlugins)
      .filter((route) => route.pluginId === "usage_reports")
      .map((route) => `${route.id}:${route.path}`)).toEqual(["usage:/usage"]);
  expect(buildPanelContributions(enabledRuntimePlugins)
      .filter((panel) => panel.pluginId === "usage_reports")
      .map((panel) => `${panel.id}:${panel.renderer}`)).toEqual(["usage:usage_reports.UsagePanel"]);
  expect(buildSidebarMoreNavContributions(enabledRuntimePlugins)
      .filter((item) => item.pluginId === "usage_reports")
      .map((item) => `${item.id}:${item.path}:${item.labelKey}`)).toEqual(["usage:/usage:nav.usage"]);
  expect(buildAppRouteContributions(disabledRuntimePlugins).some(
      (route) => route.pluginId === "usage_reports",
    )).toBe(false);
  expect(buildPanelContributions(disabledRuntimePlugins).some(
      (panel) => panel.pluginId === "usage_reports",
    )).toBe(false);
  expect(buildSidebarMoreNavContributions(disabledRuntimePlugins).some(
      (item) => item.pluginId === "usage_reports",
    )).toBe(false);
});

test("plugin chat input picker contributes a session option binding", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledAgentTeamPlugin(),
  ];

  expect(buildChatInputOptionContributions(runtimePlugins, { agentId: "team" }).map(
      (option) => `${option.id}:${option.optionBinding?.pluginId}.${option.optionBinding?.key}:${option.selectedRenderer}:${option.suppressesCorePersonaSelector}:${option.shortcut}`,
    )).toEqual(["agent_team:select-team:agent_team.SELECTED_TEAM_ID:agent_team.SelectedTeamChip:true:mod+t"]);
  expect(buildChatInputPanelContributions(runtimePlugins, { agentId: "team" }).map(
      (panel) => `${panel.id}:${panel.optionBinding?.pluginId}.${panel.optionBinding?.key}:${panel.renderer}:${panel.createPath}:${panel.managePath}`,
    )).toEqual(["agent_team:team-picker:agent_team.SELECTED_TEAM_ID:agent_team.TeamPickerModal:/agent-team:/agent-team"]);
  expect(buildChatInputOptionContributions([disabledPlugin(runtimePlugins[0])])).toEqual([]);
  expect(buildChatInputPanelContributions([disabledPlugin(runtimePlugins[0])])).toEqual([]);
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

  expect(buildAppRouteContributions(runtimePlugins).some((route) => route.path === "/plugin-chat")).toBe(false);
  expect(buildPanelContributions(runtimePlugins).some(
      (panel) => panel.renderer === "bad_chat_plugin.ChatPanel",
    )).toBe(false);
});

test("sidebar more menu keeps legacy order and visibility requirements", () => {
  expect(CORE_SIDEBAR_MORE_NAV.map((item) => item.id)).toEqual(["persona", "skills", "plugins", "mcp", "channels", "memory"]);
  expect(CORE_SIDEBAR_MORE_NAV[0].path).toBe("/persona");
  expect(CORE_SIDEBAR_MORE_NAV[0].labelKey).toBe("personaPresets.title");
  expect(CORE_SIDEBAR_MORE_NAV.some((item) => item.id === "team")).toBe(false);
  const runtimeTeamItem = buildSidebarMoreNavContributions([
    enabledAgentTeamPlugin(),
  ]).find((item) => item.id === "agent-team");
  expect(runtimeTeamItem?.requiredAnyPermissions).toEqual([Permission.TEAM_READ]);
  expect(runtimeTeamItem?.pluginId).toBe("agent_team");
  expect(CORE_SIDEBAR_MORE_NAV[CORE_SIDEBAR_MORE_NAV.length - 1].requiresSetting).toBe("memory");
});

test("AgentTeam sidebar route panel and nav follow plugin runtime state", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledAgentTeamPlugin(),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledAgentTeamPlugin()),
  ];

  expect(buildAppRouteContributions(enabledRuntimePlugins).some(
      (route) => route.id === "agent-team" && route.path === "/agent-team",
    )).toBe(true);
  expect(buildPanelContributions(enabledRuntimePlugins).some(
      (panel) => panel.id === "agent-team",
    )).toBe(true);
  expect(buildSidebarMoreNavContributions(enabledRuntimePlugins).some(
      (item) => item.id === "agent-team",
    )).toBe(true);
  expect(buildSidebarMoreNavContributions(enabledRuntimePlugins).find(
      (item) => item.id === "agent-team",
    )?.labelKey).toBe("nav.team");
  expect(buildAppRouteContributions(disabledRuntimePlugins).some(
      (route) => route.id === "agent-team",
    )).toBe(false);
  expect(buildPanelContributions(disabledRuntimePlugins).some(
      (panel) => panel.id === "agent-team",
    )).toBe(false);
  expect(buildSidebarMoreNavContributions(disabledRuntimePlugins).some(
      (item) => item.id === "agent-team",
    )).toBe(false);
});

test("AgentTeam chat input and mention contributions follow runtime state and agent context", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledAgentTeamPlugin(),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledAgentTeamPlugin()),
  ];

  expect(buildChatInputOptionContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (option) => `${option.id}:${option.optionBinding?.pluginId}.${option.optionBinding?.key}:${option.selectedRenderer}:${option.suppressesCorePersonaSelector}:${option.shortcut}`,
    )).toEqual(["agent_team:select-team:agent_team.SELECTED_TEAM_ID:agent_team.SelectedTeamChip:true:mod+t"]);
  expect(buildChatInputPanelContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (panel) => `${panel.id}:${panel.optionBinding?.pluginId}.${panel.optionBinding?.key}:${panel.renderer}:${panel.createPath}:${panel.managePath}`,
    )).toEqual(["agent_team:team-picker:agent_team.SELECTED_TEAM_ID:agent_team.TeamPickerModal:/agent-team:/agent-team"]);
  expect(buildMentionProviderContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (provider) => `${provider.id}:${provider.provider}`,
    )).toEqual(["agent_team:team-mentions:agent_team.searchTeams"]);
  expect(buildWelcomeSurfaceContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (surface) => `${surface.id}:${surface.renderer}`,
    )).toEqual(["agent_team:team-welcome:agent_team.TeamWelcomeSurface"]);
  expect(buildAssistantIdentityResolverContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (resolver) => `${resolver.id}:${resolver.resolver}`,
    )).toEqual(["agent_team:team-assistant-identity:agent_team.TeamAssistantIdentity"]);
  expect(findAssistantIdentityResolverContribution(
      "agent_team.TeamAssistantIdentity",
      enabledRuntimePlugins,
      { agentId: "team" },
    )?.pluginId).toBe("agent_team");
  expect(buildAgentCatalogEntryContributions(enabledRuntimePlugins).map(
      (entry) => `${entry.id}:${entry.pluginId}:${entry.sortOrder}`,
    )).toEqual(["team:agent_team:15"]);
  expect(findAgentCatalogEntryContribution("team", enabledRuntimePlugins)?.pluginId).toBe("agent_team");
  expect(hasAgentCatalogEntryContribution("team", enabledRuntimePlugins)).toBe(true);
  expect(hasAgentCatalogEntryContribution("team", disabledRuntimePlugins)).toBe(false);
  expect(buildAgentCatalogEntryContributions(disabledRuntimePlugins)).toEqual([]);
  expect(buildPluginContributionPreview("agent_team", enabledRuntimePlugins)
      .removedWhenDisabled.agentCatalogEntries).toEqual(["team"]);
  expect(buildPluginContributionPreview("agent_team", enabledRuntimePlugins)
      .removedWhenDisabled.assistantIdentityResolvers).toEqual(["agent_team:team-assistant-identity"]);
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
  expect(agentTeamDisablePreview.removedWhenDisabled.projectOptions).toEqual([
    "agent_team.DEFAULT_TEAM_ID",
  ]);
  expect(agentTeamDisablePreviewForTeamAgent.removedWhenDisabled.sessionOptions).toEqual([
    "agent_team.SELECTED_TEAM_ID",
  ]);
  expect(agentTeamDisablePreviewForFeishuChannel.removedWhenDisabled.channelOptions).toEqual([
    "agent_team.SELECTED_TEAM_ID",
  ]);
  expect(agentTeamDisablePreviewForTeamAgent.removedWhenDisabled.scheduledTaskOptions).toEqual([
    "agent_team.SELECTED_TEAM_ID",
  ]);
  expect(buildAgentCategoryContributions(enabledRuntimePlugins).map(
      (category) => `${category.id}:${category.label}`,
    )).toEqual(["agent_team:team-builder:agentTeam.category.teamBuilder"]);
  expect(buildAgentCatalogEntryContributions(enabledRuntimePlugins).map(
      (agent) => `${agent.id}:${agent.category}`,
    )).toEqual(["team:agent_team:team-builder"]);
  expect(buildProjectOptionContributions(enabledRuntimePlugins).map((option) => option.id)).toEqual(["agent_team.DEFAULT_TEAM_ID"]);
  expect(buildSessionOptionContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (option) => option.id,
    )).toEqual(["agent_team.SELECTED_TEAM_ID"]);
  expect(buildChannelOptionContributions(enabledRuntimePlugins, { route: "/channels/feishu" }).map(
      (option) => `${option.id}:${option.area}`,
    )).toEqual(["agent_team.SELECTED_TEAM_ID:channel_option"]);
  expect(buildScheduledTaskOptionContributions(enabledRuntimePlugins, { agentId: "team" }).map(
      (option) => `${option.id}:${option.area}`,
    )).toEqual(["agent_team.SELECTED_TEAM_ID:scheduled_task_option"]);
  expect(buildChatInputOptionContributions(enabledRuntimePlugins, { agentId: "default" })).toEqual([]);
  expect(buildSessionOptionContributions(enabledRuntimePlugins, { agentId: "default" })).toEqual([]);
  expect(buildChannelOptionContributions(enabledRuntimePlugins, { route: "/channels/slack" })).toEqual([]);
  expect(buildWelcomeSurfaceContributions(enabledRuntimePlugins, { agentId: "default" })).toEqual([]);
  expect(buildScheduledTaskOptionContributions(enabledRuntimePlugins, { agentId: "default" })).toEqual([]);
  expect(buildChatInputOptionContributions(disabledRuntimePlugins, { agentId: "team" })).toEqual([]);
  expect(buildChatInputPanelContributions(disabledRuntimePlugins, { agentId: "team" })).toEqual([]);
  expect(buildMentionProviderContributions(disabledRuntimePlugins, { agentId: "team" })).toEqual([]);
  expect(buildWelcomeSurfaceContributions(disabledRuntimePlugins, { agentId: "team" })).toEqual([]);
  expect(buildAgentCategoryContributions(disabledRuntimePlugins)).toEqual([]);
  expect(buildProjectOptionContributions(disabledRuntimePlugins)).toEqual([]);
  expect(buildChannelOptionContributions(disabledRuntimePlugins, { route: "/channels/feishu" })).toEqual([]);
  expect(buildScheduledTaskOptionContributions(disabledRuntimePlugins, { agentId: "team" })).toEqual([]);
  expect(buildProjectOptionContributions(disabledRuntimePlugins, undefined, { includeInactive: true }).map(
      (option) => `${option.id}:${option.effective}:${option.pluginStatus}`,
    )).toEqual(["agent_team.DEFAULT_TEAM_ID:false:disabled"]);
  expect(buildSessionOptionContributions(disabledRuntimePlugins, { agentId: "team" })).toEqual([]);
  expect(buildChannelOptionContributions(
      disabledRuntimePlugins,
      { route: "/channels/feishu" },
      { includeInactive: true },
    ).map((option) => `${option.id}:${option.effective}:${option.pluginStatus}`)).toEqual(["agent_team.SELECTED_TEAM_ID:false:disabled"]);
  expect(buildScheduledTaskOptionContributions(
      disabledRuntimePlugins,
      { agentId: "team" },
      { includeInactive: true },
    ).map((option) => `${option.id}:${option.effective}:${option.pluginStatus}`)).toEqual(["agent_team.SELECTED_TEAM_ID:false:disabled"]);
});

test("runtime plugin executability helpers centralize enabled and executable state", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledAgentTeamPlugin(),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledAgentTeamPlugin()),
  ];

  expect(isRuntimePluginExecutable(enabledRuntimePlugins[0])).toBe(true);
  expect(isRuntimePluginExecutableById(enabledRuntimePlugins, "agent_team")).toBe(true);
  expect(isRuntimePluginExecutableById(disabledRuntimePlugins, "agent_team")).toBe(false);
  expect(isRuntimePluginExecutableById(undefined, "agent_team")).toBe(false);
});

test("user menu contributions preserve groups and permission semantics", () => {
  expect(CORE_USER_MENU_ITEMS.map((item) => `${item.group}:${item.id}`)).toEqual([
      "admin:users",
      "admin:roles",
      "admin:agents",
      "system:notifications",
      "system:settings",
    ]);
  expect(CORE_USER_MENU_ITEMS.find((item) => item.id === "users")
      ?.requiredAnyPermissions).toEqual([Permission.USER_READ, Permission.USER_WRITE]);
  expect(CORE_USER_MENU_ITEMS.find((item) => item.id === "agents")
      ?.requiredAnyPermissions).toEqual([Permission.AGENT_ADMIN, Permission.MODEL_ADMIN]);
  expect(CORE_USER_MENU_ITEMS.some((item) => item.id === "feedback")).toBe(false);
  expect(CORE_USER_MENU_ITEMS.some((item) => item.id === "usage")).toBe(false);
});

test("default user menu is core-only and plugin menu items require runtime declarations", () => {
  expect(USER_MENU_CONTRIBUTIONS.map((item) => `${item.group}:${item.id}`)).toEqual([
      "admin:users",
      "admin:roles",
      "admin:agents",
      "system:notifications",
      "system:settings",
    ]);
  expect(USER_MENU_CONTRIBUTIONS.some((item) => item.id === "feedback")).toBe(false);
  expect(USER_MENU_CONTRIBUTIONS.some((item) => item.id === "usage")).toBe(false);
  const runtimeMenuItems = buildUserMenuContributions([
    enabledFeedbackPlugin(),
    enabledUsageReportsPlugin(),
  ]);
  expect(runtimeMenuItems.find((item) => item.id === "feedback")?.requiredAnyPermissions).toEqual([Permission.FEEDBACK_READ]);
  expect(runtimeMenuItems.find((item) => item.id === "usage")?.pluginId).toBe("usage_reports");
  expect(runtimeMenuItems.find((item) => item.id === "usage")?.requiredAnyPermissions).toEqual([Permission.USAGE_READ]);
});

test("runtime contribution builders fail closed for plugin UI when runtime state is unavailable", () => {
  expect(buildAppRouteContributions().some((route) => route.id === "team")).toBe(false);
  expect(buildPanelContributions().some((panel) => panel.id === "team")).toBe(false);
  expect(buildSidebarMoreNavContributions().some((item) => item.id === "team")).toBe(false);
  expect(buildAgentCategoryContributions().some(
      (category) => category.id === "agent_team:team-builder",
    )).toBe(false);
  expect(buildAgentCatalogEntryContributions().some((entry) => entry.id === "team")).toBe(false);
  expect(buildAppRouteContributions().some((route) => route.id === "feedback")).toBe(false);
  expect(buildPanelContributions().some((panel) => panel.id === "feedback")).toBe(false);
  expect(buildUserMenuContributions().some((item) => item.id === "feedback")).toBe(false);
  expect(buildAppRouteContributions().some((route) => route.id === "usage")).toBe(false);
  expect(buildPanelContributions().some((panel) => panel.id === "usage")).toBe(false);
  expect(buildUserMenuContributions().some((item) => item.id === "usage")).toBe(false);
});

test("runtime contribution filtering keeps enabled executable Feedback", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledFeedbackPlugin(),
  ];

  expect(buildAppRouteContributions(runtimePlugins).some(
      (route) => route.id === "feedback",
    )).toBe(true);
  expect(buildPanelContributions(runtimePlugins).some(
      (panel) => panel.id === "feedback",
    )).toBe(true);
  expect(buildUserMenuContributions(runtimePlugins).some(
      (item) => item.id === "feedback",
    )).toBe(true);
});

test("runtime contribution filtering hides disabled Usage Reports by plugin id", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledUsageReportsPlugin()),
  ];

  expect(buildAppRouteContributions(runtimePlugins).some((route) => route.id === "usage")).toBe(false);
  expect(buildPanelContributions(runtimePlugins).some((panel) => panel.id === "usage")).toBe(false);
  expect(buildUserMenuContributions(runtimePlugins).some((item) => item.id === "usage")).toBe(false);
});

test("runtime contribution filtering hides disabled or non-executable Feedback", () => {
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    { ...enabledFeedbackPlugin(), enabled: false, status: "disabled" },
  ];
  const blockedRuntimePlugins: PluginRuntimeContributionState[] = [
    { ...enabledFeedbackPlugin(), executable: false, status: "blocked" },
  ];

  for (const runtimePlugins of [disabledRuntimePlugins, blockedRuntimePlugins]) {
    expect(buildAppRouteContributions(runtimePlugins).some(
        (route) => route.id === "feedback",
      )).toBe(false);
    expect(buildPanelContributions(runtimePlugins).some(
        (panel) => panel.id === "feedback",
      )).toBe(false);
    expect(buildUserMenuContributions(runtimePlugins).some(
        (item) => item.id === "feedback",
      )).toBe(false);
  }
});

test("runtime contribution preview reports Feedback entries removed by disable simulation", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledFeedbackPlugin(),
  ];
  const preview = buildPluginContributionPreview("feedback", runtimePlugins);

  expect(preview.current.appRoutes.includes("/feedback")).toBe(true);
  expect(preview.current.panels.includes("feedback")).toBe(true);
  expect(preview.current.userMenuItems.includes("/feedback")).toBe(true);
  expect(preview.removedWhenDisabled.appRoutes).toEqual(["/feedback"]);
  expect(preview.removedWhenDisabled.panels).toEqual(["feedback"]);
  expect(preview.removedWhenDisabled.userMenuItems).toEqual(["/feedback"]);
  expect(preview.removedWhenDisabled.toolRenderers).toEqual([]);
  expect(preview.removedWhenDisabled.skillImporters).toEqual([]);
  expect(preview.removedWhenDisabled.messageActions).toEqual([
    "feedback:message-feedback",
  ]);
  expect(preview.simulatedDisabled.appRoutes.includes("/feedback")).toBe(false);
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

  expect(buildAppRouteContributions(runtimePluginsWithoutFrontend).some(
      (route) => route.id === "feedback" || route.id === "usage",
    )).toBe(false);
  expect(buildPanelContributions(runtimePluginsWithoutFrontend).some(
      (panel) => panel.id === "feedback" || panel.id === "usage",
    )).toBe(false);
  expect(buildUserMenuContributions(runtimePluginsWithoutFrontend).some(
      (item) => item.id === "feedback" || item.id === "usage",
    )).toBe(false);
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

  expect(hasMessageActionContribution("feedback")).toBe(false);
  expect(hasMessageActionContribution("feedback", enabledRuntimePlugins)).toBe(true);
  expect(hasMessageActionContribution("feedback", disabledRuntimePlugins)).toBe(false);
  expect(hasMessageActionContribution("feedback", blockedRuntimePlugins)).toBe(false);
  expect(buildMessageActionContributions(enabledRuntimePlugins).map(
      (action) => `${action.id}:${action.target}:${action.renderer}:${action.order}`,
    )).toEqual(["feedback:message-feedback:assistant_message:feedback.FeedbackButtons:20"]);
  expect(buildMessageActionContributions(enabledRuntimePlugins, {
      target: "assistant_message",
    }).map((action) => action.id)).toEqual(["feedback:message-feedback"]);
  expect(buildMessageActionContributions(enabledRuntimePlugins, {
      target: "user_message",
    }).map((action) => action.id)).toEqual([]);
  expect(buildMessageActionContributions(disabledRuntimePlugins).map((action) => action.id)).toEqual([]);
});

test("message action target context isolates plugin-declared message slots", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    {
      plugin_id: "automation_runner",
      enabled: true,
      executable: true,
      status: "enabled",
      frontend: {
        message_actions: [
          {
            id: "automation_runner:retry-user-message",
            target: "user_message",
            renderer: "automation_runner.RetryUserMessage",
            order: 30,
          },
          {
            id: "automation_runner:inspect-tool-result",
            target: "tool_result",
            renderer: "automation_runner.InspectToolResult",
            order: 20,
          },
        ],
      },
    },
  ];

  expect(buildMessageActionContributions(runtimePlugins, {
      target: "assistant_message",
    })).toEqual([]);
  expect(buildMessageActionContributions(runtimePlugins, { target: "user_message" }).map(
      (action) => action.id,
    )).toEqual(["automation_runner:retry-user-message"]);
  expect(buildMessageActionContributions(runtimePlugins, { target: "tool_result" }).map(
      (action) => action.id,
    )).toEqual(["automation_runner:inspect-tool-result"]);
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

  expect(hasMessageActionContribution("feedback", runtimePluginsWithoutFrontend)).toBe(false);
  expect(buildMessageActionContributions(runtimePluginsWithoutFrontend).map(
      (action) => action.id,
    )).toEqual([]);
  expect(hasMessageActionContribution("feedback", runtimePluginsWithLegacyString)).toBe(false);
  expect(buildMessageActionContributions(runtimePluginsWithLegacyString)).toEqual([]);
});

test("plugin message renderer contributions are runtime gated", () => {
  const plugin: PluginRuntimeContributionState = {
    plugin_id: "automation_runner",
    enabled: true,
    executable: true,
    status: "enabled",
    frontend: {
      message_renderers: [
        {
          id: "automation_runner:run-card",
          renderer: "automation_runner.RunCard",
          message_types: ["run_result"],
        },
      ],
    },
  };

  expect(buildPluginMessageRendererContributions([plugin])).toEqual([
    {
      id: "run-card",
      pluginId: "automation_runner",
      renderer: "automation_runner.RunCard",
      messageTypes: ["run_result"],
      area: "plugin_message_renderer",
    },
  ]);
  expect(hasPluginMessageRenderer(
      "automation_runner",
      "automation_runner.RunCard",
      [plugin],
    )).toBe(true);
  expect(getPluginMessageRenderer(
      "automation_runner",
      "automation_runner.RunCard",
      [disabledPlugin(plugin)],
    )).toBe(undefined);
});

test("runtime contribution preview reports Usage Reports entries removed by disable simulation", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledUsageReportsPlugin(),
  ];
  const preview = buildPluginContributionPreview("usage_reports", runtimePlugins);

  expect(preview.current.appRoutes.includes("/usage")).toBe(true);
  expect(preview.current.panels.includes("usage")).toBe(true);
  expect(preview.current.userMenuItems.includes("/usage")).toBe(true);
  expect(preview.removedWhenDisabled.appRoutes).toEqual(["/usage"]);
  expect(preview.removedWhenDisabled.panels).toEqual(["usage"]);
  expect(preview.removedWhenDisabled.userMenuItems).toEqual(["/usage"]);
});

test("settings sections preserve the legacy category order", () => {
  expect(CORE_SETTINGS_SECTIONS.map((section) => section.category)).toEqual([
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
    ]);
  expect(CORE_SETTINGS_SECTIONS.some(
      (section) => (section.category as string) === "audio_transcription",
    )).toBe(false);
});

test("core tool renderer contributions map current dedicated tool cards", () => {
  const toolNames = CORE_TOOL_RENDERERS.flatMap((renderer) => renderer.toolNames);

  expect(getCoreToolRendererId("scheduled_task_create")).toEqual("scheduled-task");
  expect(getCoreToolRendererId("env_var_delete")).toEqual("env-var");
  expect(getCoreToolRendererId("create_agent_team")).toBe(undefined);
  expect(getCoreToolRendererId("memory_delete")).toEqual("memory-store");
  expect(getCoreToolRendererId("image_generate")).toBe(undefined);
  expect(getCoreToolRendererId("audio_transcribe")).toBe(undefined);
  expect(hasCoreToolRenderer("ask_human")).toBe(true);
  expect(hasCoreToolRenderer("image_generate")).toBe(false);
  expect(hasCoreToolRenderer("audio_transcribe")).toBe(false);
  expect(hasCoreToolRenderer("create_agent_team")).toBe(false);
  expect(hasCoreToolRenderer("unknown_tool")).toBe(false);
  expect(toolNames.includes("read_file")).toBeTruthy();
  expect(toolNames.includes("search_tools")).toBeTruthy();
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

  expect(getToolRendererId("create_agent_team")).toBe(undefined);
  expect(getToolRendererId("image_generate")).toBe(undefined);
  expect(getToolRendererId("audio_transcribe")).toBe(undefined);
  expect(getToolRendererId("create_agent_team", enabledRuntimePlugins)).toBe("agent-team");
  expect(getToolRendererId("image_generate", enabledRuntimePlugins)).toBe("image-generate");
  expect(getToolRendererId("audio_transcribe", enabledRuntimePlugins)).toBe("audio-transcribe");
  expect(getToolRendererId("create_agent_team", disabledRuntimePlugins)).toBe(undefined);
  expect(getToolRendererId("image_generate", disabledRuntimePlugins)).toBe(undefined);
  expect(getToolRendererId("audio_transcribe", disabledRuntimePlugins)).toBe(undefined);
  expect(hasToolRenderer("image_generate", enabledRuntimePlugins)).toBe(true);
  expect(hasToolRenderer("audio_transcribe", enabledRuntimePlugins)).toBe(true);
  expect(hasToolRenderer("create_agent_team", enabledRuntimePlugins)).toBe(true);
  expect(hasToolRenderer("create_agent_team", disabledRuntimePlugins)).toBe(false);
  expect(hasToolRenderer("image_generate", disabledRuntimePlugins)).toBe(false);
  expect(hasToolRenderer("audio_transcribe", disabledRuntimePlugins)).toBe(false);
  expect(buildToolRendererContributions(disabledRuntimePlugins).map(
      (renderer) => renderer.id,
    )).toEqual(CORE_TOOL_RENDERERS.map((renderer) => renderer.id));
});

test("runtime contribution preview reports plugin tool renderers removed by disable", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledToolPlugin("image_generation"),
  ];
  const preview = buildPluginContributionPreview("image_generation", runtimePlugins);

  expect(preview.current.toolRenderers.includes("image-generate")).toBe(true);
  expect(preview.removedWhenDisabled.toolRenderers).toEqual(["image-generate"]);
  expect(preview.simulatedDisabled.toolRenderers.includes("image-generate")).toBe(false);
});

test("runtime contribution preview reports audio transcription renderer removed by disable", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledToolPlugin("audio_transcription"),
  ];
  const preview = buildPluginContributionPreview("audio_transcription", runtimePlugins);

  expect(preview.current.toolRenderers.includes("audio-transcribe")).toBe(true);
  expect(preview.removedWhenDisabled.toolRenderers).toEqual(["audio-transcribe"]);
  expect(preview.simulatedDisabled.toolRenderers.includes("audio-transcribe")).toBe(false);
});

test("advanced file viewers follow plugin runtime state", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledAdvancedFileViewersPlugin(),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledAdvancedFileViewersPlugin()),
  ];

  expect(buildFileViewerContributions(enabledRuntimePlugins).map((viewer) => viewer.id)).toEqual([
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
  expect(hasFileViewerContribution("pdf")).toBe(false);
  expect(hasFileViewerContribution("pdf", enabledRuntimePlugins)).toBe(true);
  expect(hasFileViewerContribution("pdf", disabledRuntimePlugins)).toBe(false);
  expect(buildFileViewerContributions(disabledRuntimePlugins).map((viewer) => viewer.id)).toEqual([]);
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

  expect(buildUploadHandlerContributions(runtimePlugins)).toEqual([
    {
      id: "upload_demo:markdown-import",
      pluginId: "upload_demo",
      accept: [".md", "text/markdown"],
      maxBytes: 1048576,
      handler: "upload_demo.markdownImport",
      area: "upload_handler",
    },
  ]);
  expect(buildUploadHandlerContributions([disabledPlugin(runtimePlugins[0])])).toEqual([]);
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

  expect(buildToolRendererContributions(runtimePlugins).at(-1)).toEqual({
    id: "custom-image-card",
    toolNames: ["image_generation.custom_image"],
    area: "tool_renderer",
  });
  expect(buildFileViewerContributions(runtimePlugins)).toEqual([
    { id: "diagram", extensions: ["drawio"], area: "file_viewer" },
  ]);
  expect(buildSkillImporterContributions(runtimePlugins)).toEqual([
    { id: "zip-import", source: "zip", area: "skill_importer" },
  ]);
  expect(buildChannelConnectorContributions(runtimePlugins)).toEqual([
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

  expect(preview.current.fileViewers.includes("pdf")).toBe(true);
  expect(preview.removedWhenDisabled.fileViewers).toEqual([
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
  expect(preview.simulatedDisabled.fileViewers.includes("pdf")).toBe(false);
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

  expect(getToolRendererId("image_generate", runtimePluginsWithoutFrontend)).toBe(undefined);
  expect(hasFileViewerContribution("pdf", runtimePluginsWithoutFrontend)).toBe(false);
  expect(buildToolRendererContributions(runtimePluginsWithoutFrontend).some(
      (renderer) => renderer.id === "image-generate",
    )).toBe(false);
  expect(buildFileViewerContributions(runtimePluginsWithoutFrontend)).toEqual([]);
  expect(buildSkillImporterContributions(runtimePluginsWithoutFrontend)).toEqual([]);
  expect(buildChannelConnectorContributions(runtimePluginsWithoutFrontend)).toEqual([]);
  expect(buildI18nNamespaceContributions(runtimePluginsWithoutFrontend)).toEqual([]);
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

  expect(buildToolRendererContributions(runtimePluginsWithLegacyStrings)).toEqual(CORE_TOOL_RENDERERS);
  expect(buildFileViewerContributions(runtimePluginsWithLegacyStrings)).toEqual([]);
  expect(buildSkillImporterContributions(runtimePluginsWithLegacyStrings)).toEqual([]);
  expect(buildChannelConnectorContributions(runtimePluginsWithLegacyStrings)).toEqual([]);
});

test("plugin i18n namespaces follow runtime frontend metadata", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledAdvancedFileViewersPlugin(),
    enabledGithubInstallerPlugin(),
    enabledFeishuConnectorPlugin(),
  ];
  const disabledRuntimePlugins = runtimePlugins.map(disabledPlugin);

  expect(hasI18nNamespaceContribution("advanced_file_viewers:documents")).toBe(false);
  expect(hasI18nNamespaceContribution("advanced_file_viewers:documents", runtimePlugins)).toBe(true);
  expect(hasI18nNamespaceContribution("advanced_file_viewers:documents", disabledRuntimePlugins)).toBe(false);
  expect(buildI18nNamespaceContributions(runtimePlugins).map((item) => item.id)).toEqual([
      "advanced_file_viewers:documents",
      "github_installer:skills",
      "feishu_connector:channels",
    ]);
  expect(buildI18nNamespaceContributions(disabledRuntimePlugins)).toEqual([]);
});

test("runtime contribution preview reports i18n namespaces removed by disable", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledAdvancedFileViewersPlugin(),
  ];

  const preview = buildPluginContributionPreview(
    "advanced_file_viewers",
    runtimePlugins,
  );

  expect(preview.current.i18nNamespaces).toEqual([
    "advanced_file_viewers:documents",
  ]);
  expect(preview.removedWhenDisabled.i18nNamespaces).toEqual([
    "advanced_file_viewers:documents",
  ]);
  expect(preview.simulatedDisabled.i18nNamespaces).toEqual([]);
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

  expect(hasPluginAssetSlotContribution("file_viewer", enabledRuntimePlugins)).toBe(true);
  expect(hasPluginAssetSlotContribution("file_viewer", disabledRuntimePlugins)).toBe(false);
  expect(contributions.map((contribution) => ({
      id: contribution.id,
      pluginId: contribution.pluginId,
      slot: contribution.slot,
      assetSchema: contribution.assetSchema,
      assets: contribution.assets,
      mountPath: contribution.mountPath,
      area: contribution.area,
    }))).toEqual([
      {
        id: "advanced_file_viewers:file_viewer",
        pluginId: "advanced_file_viewers",
        slot: "file_viewer",
        assetSchema: "lambchat.plugin.frontend-assets.v1",
        assets: ["widget.js"],
        mountPath: "/plugin-assets/advanced_file_viewers/",
        area: "plugin_asset_slot",
      },
    ]);
  expect(buildPluginAssetSlotContributions(disabledRuntimePlugins)).toEqual([]);
  expect(buildPluginAssetSlotContributions(mismatchedRuntimePlugins)).toEqual([]);
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

  expect(preview.current.pluginAssetSlots).toEqual([
    "advanced_file_viewers:file_viewer",
  ]);
  expect(preview.removedWhenDisabled.pluginAssetSlots).toEqual([
    "advanced_file_viewers:file_viewer",
  ]);
  expect(preview.simulatedDisabled.pluginAssetSlots).toEqual([]);
});

test("GitHub skill importer follows plugin runtime state", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledGithubInstallerPlugin(),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledGithubInstallerPlugin()),
  ];

  expect(buildSkillImporterContributions(enabledRuntimePlugins).map((importer) => importer.id)).toEqual([
    "github-import",
  ]);
  expect(hasSkillImporterContribution("github-import")).toBe(false);
  expect(hasSkillImporterContribution("github-import", enabledRuntimePlugins)).toBe(true);
  expect(hasSkillImporterContribution("github-import", disabledRuntimePlugins)).toBe(false);
  expect(buildSkillImporterContributions(disabledRuntimePlugins).map(
      (importer) => importer.id,
    )).toEqual([]);
});

test("Feishu channel connector follows plugin runtime state", () => {
  const enabledRuntimePlugins: PluginRuntimeContributionState[] = [
    enabledFeishuConnectorPlugin(),
  ];
  const disabledRuntimePlugins: PluginRuntimeContributionState[] = [
    disabledPlugin(enabledFeishuConnectorPlugin()),
  ];

  expect(buildChannelConnectorContributions(enabledRuntimePlugins).map((connector) => connector.id)).toEqual([
    "feishu_connector:feishu",
  ]);
  expect(findChannelConnectorContribution("feishu", enabledRuntimePlugins)?.panelRenderer).toBe("feishu_connector.FeishuPanel");
  expect(hasChannelConnectorContribution("feishu")).toBe(false);
  expect(hasRuntimeManagedChannelConnector("feishu")).toBe(false);
  expect(hasRuntimeManagedChannelConnector("feishu", enabledRuntimePlugins)).toBe(true);
  expect(hasRuntimeManagedChannelConnector("feishu", disabledRuntimePlugins)).toBe(true);
  expect(hasChannelConnectorContribution("feishu", enabledRuntimePlugins)).toBe(true);
  expect(hasChannelConnectorContribution("feishu", disabledRuntimePlugins)).toBe(false);
  expect(buildChannelConnectorContributions(disabledRuntimePlugins).map(
      (connector) => connector.id,
    )).toEqual([]);
});

test("runtime contribution preview reports Feishu connector removed by disable", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledFeishuConnectorPlugin(),
  ];
  const preview = buildPluginContributionPreview("feishu_connector", runtimePlugins);

  expect(preview.current.channelConnectors.includes("feishu_connector:feishu")).toBe(true);
  expect(preview.removedWhenDisabled.channelConnectors).toEqual([
    "feishu_connector:feishu",
  ]);
  expect(preview.simulatedDisabled.channelConnectors.includes("feishu_connector:feishu")).toBe(false);
});

test("runtime contribution preview reports GitHub skill importer removed by disable", () => {
  const runtimePlugins: PluginRuntimeContributionState[] = [
    enabledGithubInstallerPlugin(),
  ];
  const preview = buildPluginContributionPreview("github_installer", runtimePlugins);

  expect(preview.current.skillImporters.includes("github-import")).toBe(true);
  expect(preview.removedWhenDisabled.skillImporters).toEqual(["github-import"]);
  expect(preview.simulatedDisabled.skillImporters.includes("github-import")).toBe(false);
});

test("core route ids remain valid non-chat tab values", () => {
  const tabs: readonly TabType[] = APP_ROUTE_CONTRIBUTIONS.map((route) => route.tab);

  expect(tabs.includes("chat")).toBe(false);
  expect(new Set(tabs).size).toBe(tabs.length);
});

test("core contribution module does not keep static built-in plugin UI fallback tables", async () => {
  const { readFileSync } = await import("node:fs");
  const source = readFileSync(
    new URL("../coreContributions.ts", import.meta.url),
    "utf8",
  );

  expect(source).not.toMatch(/BUILTIN_PLUGIN_/);
  expect(source).toMatch(/plugin\.frontend\?\.app_tabs/);
  expect(source).toMatch(/plugin\.frontend\?\.tool_renderers/);
  expect(source).toMatch(/plugin\.frontend\?\.file_viewers/);
  expect(source).toMatch(/plugin\.frontend\?\.message_actions/);
});
