import { Suspense, lazy, type ReactNode } from "react";
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
  import("../../panels/FeedbackPanel").then((m) => ({
    default: m.FeedbackPanel,
  })),
);
const ChannelsPage = lazy(() =>
  import("../../pages/ChannelsPage").then((m) => ({ default: m.ChannelsPage })),
);
const RevealedFilesPage = lazy(() =>
  import("../../fileLibrary/RevealedFilesPanel").then((m) => ({
    default: m.RevealedFilesPanel,
  })),
);
const BookmarksPanel = lazy(() =>
  import("../../panels/BookmarksPanel").then((m) => ({
    default: m.BookmarksPanel,
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

const panelMap: Record<
  string,
  React.LazyExoticComponent<React.ComponentType>
> = {
  skills: SkillsHubPanel,
  marketplace: SkillsHubPanel,
  users: UsersPanel,
  roles: RolesPanel,
  settings: SettingsPanel,
  mcp: MCPPanel,
  feedback: FeedbackPanel,
  channels: ChannelsPage,
  agents: AgentModelPanel,
  files: RevealedFilesPage,
  bookmarks: BookmarksPanel,
  persona: PersonaPlazaPanel,
  team: TeamBuilderPanel,
  notifications: NotificationPanel,
  memory: MemoryPanel,
  "scheduled-tasks": ScheduledTaskPanel,
  usage: UsagePanel,
};

const skeletonMap: Partial<Record<TabType, ReactNode>> = {
  skills: <SkillsPanelSkeleton />,
  marketplace: <MarketplacePanelSkeleton />,
  users: <UsersPanelSkeleton />,
  roles: <RolesPanelSkeleton />,
  mcp: <MCPPanelSkeleton />,
  feedback: <FeedbackPanelSkeleton />,
  "scheduled-tasks": <ScheduledTaskPanelSkeleton />,
  channels: <ChannelsGridSkeleton />,
  agents: <AgentModelPanelSkeleton />,
  usage: <UsagePanelSkeleton />,
};

export function TabContent({ activeTab }: { activeTab: TabType }) {
  if (activeTab === "chat") return null;

  const Panel = panelMap[activeTab];
  if (!Panel) return null;

  return (
    <main className="flex-1 overflow-hidden bg-[var(--theme-bg)]">
      <div className="mx-auto w-full h-full flex flex-col overflow-hidden lg:max-w-[80rem] xl:max-w-[96rem] 2xl:max-w-[120rem] sm:px-4">
        <Suspense fallback={skeletonMap[activeTab] ?? <PanelLoadingState />}>
          <Panel />
        </Suspense>
      </div>
    </main>
  );
}
