import { Suspense, lazy, useMemo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  SkillsPanelSkeleton,
  MarketplacePanelSkeleton,
  UsersPanelSkeleton,
  RolesPanelSkeleton,
  MCPPanelSkeleton,
  FeedbackPanelSkeleton,
  ScheduledTaskPanelSkeleton,
  ChannelsGridSkeleton,
  AgentModelPanelSkeleton,
  UsagePanelSkeleton,
} from "../../skeletons";
import { PanelLoadingState } from "../../common/PanelLoadingState";
import {
  buildPanelContributions,
  type PluginRuntimeContributionStates,
} from "../../../extensions/coreContributions";
import type { TabType } from "./types";

const SkillsHubPanel = lazy(() =>
  import("../../panels/SkillsHubPanel").then((m) => ({
    default: m.SkillsHubPanel,
  })),
);
const UsersPanel = lazy(() =>
  import("../../panels/UsersPanel").then((m) => ({ default: m.UsersPanel })),
);
const RolesPanel = lazy(() =>
  import("../../panels/RolesPanel").then((m) => ({ default: m.RolesPanel })),
);
const SettingsPanel = lazy(() =>
  import("../../panels/SettingsPanel").then((m) => ({
    default: m.SettingsPanel,
  })),
);
const AgentModelPanel = lazy(() =>
  import("../../panels/AgentModelPanel").then((m) => ({
    default: m.AgentModelPanel,
  })),
);
const MCPPanel = lazy(() =>
  import("../../panels/MCPPanel").then((m) => ({ default: m.MCPPanel })),
);
const FeedbackPanel = lazy(() =>
  import("../../../plugins/feedback/FeedbackPanel").then((m) => ({
    default: m.FeedbackPanel,
  })),
);
const WorkflowPanel = lazy(() =>
  import("../../../plugins/workflow/WorkflowPanel").then((m) => ({
    default: m.WorkflowPanel,
  })),
);
const ChannelsPage = lazy(() =>
  import("../../pages/ChannelsPage").then((m) => ({ default: m.ChannelsPage })),
);
const RevealedFilesPanel = lazy(() =>
  import("../../fileLibrary/RevealedFilesPanel").then((m) => ({
    default: m.RevealedFilesPanel,
  })),
);
const NotificationPanel = lazy(() =>
  import("../../panels/NotificationPanel").then((m) => ({
    default: m.NotificationPanel,
  })),
);
const MemoryPanel = lazy(() =>
  import("../../panels/MemoryPanel").then((m) => ({
    default: m.MemoryPanel,
  })),
);
const ScheduledTaskPanel = lazy(() =>
  import("../../panels/ScheduledTaskPanel").then((m) => ({
    default: m.ScheduledTaskPanel,
  })),
);
const PersonaPlazaPanel = lazy(() =>
  import("../../persona/PersonaPlazaPanel").then((m) => ({
    default: m.PersonaPlazaPanel,
  })),
);
const TeamBuilderPanel = lazy(() =>
  import("../../team/TeamBuilderWrapper").then((m) => ({
    default: m.TeamBuilderWrapper,
  })),
);
const UsagePanel = lazy(() =>
  import("../../panels/UsagePanel").then((m) => ({
    default: m.UsagePanel,
  })),
);

type RuntimeAwarePanelProps = {
  runtimePlugins?: PluginRuntimeContributionStates;
};

type PanelComponent = React.LazyExoticComponent<
  React.ComponentType<Record<string, never>>
> | React.ComponentType<Record<string, never>>;

type RuntimeAwarePanelComponent = React.LazyExoticComponent<
  React.ComponentType<RuntimeAwarePanelProps>
>;

const corePanelComponents: Partial<Record<Exclude<TabType, "chat">, PanelComponent>> = {
  skills: SkillsHubPanel,
  marketplace: SkillsHubPanel,
  plugins: SkillsHubPanel,
  users: UsersPanel,
  roles: RolesPanel,
  settings: SettingsPanel,
  mcp: MCPPanel,
  channels: ChannelsPage,
  agents: AgentModelPanel,
  files: RevealedFilesPanel,
  persona: PersonaPlazaPanel,
  notifications: NotificationPanel,
  memory: MemoryPanel,
  "scheduled-tasks": ScheduledTaskPanel,
};

const pluginPanelRenderers: Record<string, PanelComponent> = {
  "agent_team.TeamBuilderPanel": TeamBuilderPanel,
  "workflow.WorkflowPanel": WorkflowPanel,
  "feedback.FeedbackPanel": FeedbackPanel,
  "usage_reports.UsagePanel": UsagePanel,
};

function PluginPanelUnavailable({
  renderer,
  tab,
}: {
  renderer: string;
  tab: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex h-full items-center justify-center px-4">
      <div className="max-w-md rounded-lg border border-dashed border-stone-300 bg-stone-50/70 p-5 text-center text-sm text-stone-600 shadow-sm dark:border-stone-700 dark:bg-stone-900/45 dark:text-stone-300">
        <div className="mb-2 text-base font-semibold text-stone-800 dark:text-stone-100">
          {t("pluginRuntime.panelUnavailable", "Plugin panel unavailable")}
        </div>
        <div className="space-y-1 text-xs text-stone-500 dark:text-stone-400">
          <p>{t("pluginRuntime.panelUnavailableHint", "The plugin declared a panel renderer that is not registered in this build.")}</p>
          <p className="font-mono break-all">{renderer}</p>
          <p className="font-mono break-all">{tab}</p>
        </div>
      </div>
    </div>
  );
}

function missingPluginPanelRenderer(panel: { renderer?: string; tab: string }): PanelComponent {
  const renderer = panel.renderer ?? "";
  const tab = panel.tab;
  return function MissingPluginPanelRenderer() {
    return <PluginPanelUnavailable renderer={renderer} tab={tab} />;
  };
}

function renderPanel(
  activeTab: Exclude<TabType, "chat">,
  Panel: PanelComponent,
  runtimePlugins?: PluginRuntimeContributionStates,
) {
  if (activeTab === "workflows" || activeTab === "workflows-editor" || activeTab === "workflows-run") {
    const WorkflowAwarePanel = Panel as unknown as React.ComponentType<{ activeTab: Exclude<TabType, "chat"> }>;
    return <WorkflowAwarePanel activeTab={activeTab} />;
  }
  if (activeTab === "skills" || activeTab === "marketplace" || activeTab === "plugins") {
    const RuntimeAwareSkillsHubPanel = SkillsHubPanel as RuntimeAwarePanelComponent;
    return <RuntimeAwareSkillsHubPanel runtimePlugins={runtimePlugins} />;
  }
  if (activeTab === "files") {
    const RuntimeAwareRevealedFilesPanel = RevealedFilesPanel as RuntimeAwarePanelComponent;
    return <RuntimeAwareRevealedFilesPanel runtimePlugins={runtimePlugins} />;
  }
  if (activeTab === "channels") {
    const RuntimeAwareChannelsPage = ChannelsPage as RuntimeAwarePanelComponent;
    return <RuntimeAwareChannelsPage runtimePlugins={runtimePlugins} />;
  }
  if (activeTab === "agents") {
    const RuntimeAwareAgentModelPanel = AgentModelPanel as RuntimeAwarePanelComponent;
    return <RuntimeAwareAgentModelPanel runtimePlugins={runtimePlugins} />;
  }
  return <Panel />;
}

function buildPanelMap(runtimePlugins?: PluginRuntimeContributionStates) {
  return buildPanelContributions(runtimePlugins).reduce<
    Partial<Record<TabType, PanelComponent>>
  >((map, panel) => {
    const rendererPanel = panel.renderer ? pluginPanelRenderers[panel.renderer] : undefined;
    const corePanel = corePanelComponents[panel.tab];
    if (rendererPanel || corePanel || panel.renderer) {
      map[panel.tab] = rendererPanel ?? corePanel ?? missingPluginPanelRenderer(panel);
    }
    return map;
  }, {});
}

const skeletonMap: Partial<Record<TabType, ReactNode>> = {
  skills: <SkillsPanelSkeleton />,
  marketplace: <MarketplacePanelSkeleton />,
  plugins: <MarketplacePanelSkeleton />,
  users: <UsersPanelSkeleton />,
  roles: <RolesPanelSkeleton />,
  mcp: <MCPPanelSkeleton />,
  feedback: <FeedbackPanelSkeleton />,
  "scheduled-tasks": <ScheduledTaskPanelSkeleton />,
  channels: <ChannelsGridSkeleton />,
  agents: <AgentModelPanelSkeleton />,
  usage: <UsagePanelSkeleton />,
};

export function TabContent({
  activeTab,
  runtimePlugins,
}: {
  activeTab: TabType;
  runtimePlugins?: PluginRuntimeContributionStates;
}) {
  const panelMap = useMemo(
    () => buildPanelMap(runtimePlugins),
    [runtimePlugins],
  );

  if (activeTab === "chat") return null;

  const Panel = panelMap[activeTab];
  if (!Panel) return null;

  return (
    <main className="flex-1 overflow-hidden bg-[var(--theme-bg)]">
      <div className="mx-auto w-full h-full flex flex-col overflow-hidden lg:max-w-[80rem] xl:max-w-[96rem] 2xl:max-w-[120rem] sm:px-4">
        <Suspense fallback={skeletonMap[activeTab] ?? <PanelLoadingState />}>
          {renderPanel(activeTab, Panel, runtimePlugins)}
        </Suspense>
      </div>
    </main>
  );
}
