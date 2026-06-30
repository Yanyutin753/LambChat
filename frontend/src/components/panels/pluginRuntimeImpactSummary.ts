import { buildPluginContributionPreview, type PluginContributionSnapshot } from "../../extensions/coreContributions";
import type { PluginRuntimeListResponse, PluginRuntimePlugin } from "../../types";
import { declaredRuntimeEntryLabels, resourceActionLabels, uniqueValues } from "./pluginRuntimePanelUtils";

function emptyContributionSnapshot(): PluginContributionSnapshot {
  return {
    appRoutes: [],
    panels: [],
    sidebarMoreItems: [],
    userMenuItems: [],
    toolRenderers: [],
    fileViewers: [],
    skillImporters: [],
    channelConnectors: [],
    messageActions: [],
    chatInputOptions: [],
    chatInputPanels: [],
    mentionProviders: [],
    welcomeSurfaces: [],
    assistantIdentityResolvers: [],
    agentCatalogEntries: [],
    agentCategories: [],
    projectOptions: [],
    sessionOptions: [],
    channelOptions: [],
    scheduledTaskOptions: [],
    pluginAssetSlots: [],
    i18nNamespaces: [],
  };
}

export function buildPluginRuntimeImpactSummary(
  plugin: PluginRuntimePlugin,
  runtimePlugins?: PluginRuntimeListResponse["plugins"],
) {
  const contributionPreviews = [
    buildPluginContributionPreview(plugin.plugin_id, runtimePlugins),
    buildPluginContributionPreview(plugin.plugin_id, runtimePlugins, { agentId: "team" }),
    buildPluginContributionPreview(plugin.plugin_id, runtimePlugins, { route: "/channels/feishu" }),
  ];
  const removedWhenDisabled = contributionPreviews.reduce(
    (acc: PluginContributionSnapshot, preview): PluginContributionSnapshot => ({
      appRoutes: uniqueValues([...acc.appRoutes, ...preview.removedWhenDisabled.appRoutes]),
      panels: uniqueValues([...acc.panels, ...preview.removedWhenDisabled.panels]),
      sidebarMoreItems: uniqueValues([...acc.sidebarMoreItems, ...preview.removedWhenDisabled.sidebarMoreItems]),
      userMenuItems: uniqueValues([...acc.userMenuItems, ...preview.removedWhenDisabled.userMenuItems]),
      toolRenderers: uniqueValues([...acc.toolRenderers, ...preview.removedWhenDisabled.toolRenderers]),
      fileViewers: uniqueValues([...acc.fileViewers, ...preview.removedWhenDisabled.fileViewers]),
      skillImporters: uniqueValues([...acc.skillImporters, ...preview.removedWhenDisabled.skillImporters]),
      channelConnectors: uniqueValues([...acc.channelConnectors, ...preview.removedWhenDisabled.channelConnectors]),
      messageActions: uniqueValues([...acc.messageActions, ...preview.removedWhenDisabled.messageActions]),
      chatInputOptions: uniqueValues([...acc.chatInputOptions, ...preview.removedWhenDisabled.chatInputOptions]),
      chatInputPanels: uniqueValues([...acc.chatInputPanels, ...preview.removedWhenDisabled.chatInputPanels]),
      mentionProviders: uniqueValues([...acc.mentionProviders, ...preview.removedWhenDisabled.mentionProviders]),
      welcomeSurfaces: uniqueValues([...acc.welcomeSurfaces, ...preview.removedWhenDisabled.welcomeSurfaces]),
      assistantIdentityResolvers: uniqueValues([...acc.assistantIdentityResolvers, ...preview.removedWhenDisabled.assistantIdentityResolvers]),
      agentCatalogEntries: uniqueValues([...acc.agentCatalogEntries, ...preview.removedWhenDisabled.agentCatalogEntries]),
      agentCategories: uniqueValues([...acc.agentCategories, ...preview.removedWhenDisabled.agentCategories]),
      projectOptions: uniqueValues([...acc.projectOptions, ...preview.removedWhenDisabled.projectOptions]),
      sessionOptions: uniqueValues([...acc.sessionOptions, ...preview.removedWhenDisabled.sessionOptions]),
      channelOptions: uniqueValues([...acc.channelOptions, ...preview.removedWhenDisabled.channelOptions]),
      scheduledTaskOptions: uniqueValues([...acc.scheduledTaskOptions, ...preview.removedWhenDisabled.scheduledTaskOptions]),
      pluginAssetSlots: uniqueValues([...acc.pluginAssetSlots, ...preview.removedWhenDisabled.pluginAssetSlots]),
      i18nNamespaces: uniqueValues([...acc.i18nNamespaces, ...preview.removedWhenDisabled.i18nNamespaces]),
    }),
    emptyContributionSnapshot(),
  );
  const declaredEntries = declaredRuntimeEntryLabels(plugin);

  return {
    activeEntries: plugin.executable ? declaredEntries : [],
    blockedWhenDisabled: uniqueValues([
      ...declaredEntries,
      ...removedWhenDisabled.toolRenderers.map(
        (value) => `renderer ${value}`,
      ),
      ...removedWhenDisabled.fileViewers.map(
        (value) => `viewer ${value}`,
      ),
      ...removedWhenDisabled.skillImporters.map(
        (value) => `importer ${value}`,
      ),
      ...removedWhenDisabled.channelConnectors.map(
        (value) => `connector ${value}`,
      ),
      ...removedWhenDisabled.messageActions.map(
        (value) => `action ${value}`,
      ),
      ...removedWhenDisabled.chatInputOptions.map(
        (value) => `chat option ${value}`,
      ),
      ...removedWhenDisabled.chatInputPanels.map(
        (value) => `chat panel ${value}`,
      ),
      ...removedWhenDisabled.mentionProviders.map(
        (value) => `mention ${value}`,
      ),
      ...removedWhenDisabled.welcomeSurfaces.map(
        (value) => `welcome surface ${value}`,
      ),
      ...removedWhenDisabled.assistantIdentityResolvers.map(
        (value) => `assistant identity ${value}`,
      ),
      ...removedWhenDisabled.agentCatalogEntries.map(
        (value) => `agent ${value}`,
      ),
      ...removedWhenDisabled.agentCategories.map(
        (value) => `agent category ${value}`,
      ),
      ...removedWhenDisabled.projectOptions.map(
        (value) => `project option ${value}`,
      ),
      ...removedWhenDisabled.sessionOptions.map(
        (value) => `session option ${value}`,
      ),
      ...removedWhenDisabled.channelOptions.map(
        (value) => `channel option ${value}`,
      ),
      ...removedWhenDisabled.scheduledTaskOptions.map(
        (value) => `scheduled task option ${value}`,
      ),
      ...removedWhenDisabled.pluginAssetSlots.map(
        (value) => `asset slot ${value}`,
      ),
      ...removedWhenDisabled.i18nNamespaces.map(
        (value) => `i18n ${value}`,
      ),
      ...removedWhenDisabled.appRoutes.map(
        (value) => `app route ${value}`,
      ),
      ...removedWhenDisabled.panels.map(
        (value) => `panel ${value}`,
      ),
      ...removedWhenDisabled.sidebarMoreItems.map(
        (value) => `sidebar ${value}`,
      ),
      ...removedWhenDisabled.userMenuItems.map(
        (value) => `menu ${value}`,
      ),
    ]),
    resourceActions: resourceActionLabels(plugin.dry_run_actions),
  };
}
