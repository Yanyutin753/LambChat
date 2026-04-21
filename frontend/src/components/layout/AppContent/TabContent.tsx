import { Suspense, lazy } from "react";
import { Loading } from "../../common";
import type { TabType } from "./types";

const SkillsPanel = lazy(() =>
  import("../../panels/SkillsPanel").then((m) => ({ default: m.SkillsPanel })),
);
const MarketplacePanel = lazy(() =>
  import("../../panels/MarketplacePanel").then((m) => ({
    default: m.MarketplacePanel,
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
const AgentConfigPanel = lazy(() =>
  import("../../panels/AgentPanel").then((m) => ({
    default: m.AgentConfigPanel,
  })),
);
const ModelPanel = lazy(() =>
  import("../../panels/ModelPanel").then((m) => ({
    default: m.ModelPanel,
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

const panelMap: Record<
  string,
  React.LazyExoticComponent<React.ComponentType>
> = {
  skills: SkillsPanel,
  marketplace: MarketplacePanel,
  users: UsersPanel,
  roles: RolesPanel,
  settings: SettingsPanel,
  mcp: MCPPanel,
  feedback: FeedbackPanel,
  channels: ChannelsPage,
  agents: AgentConfigPanel,
  models: ModelPanel,
  files: RevealedFilesPage,
  notifications: NotificationPanel,
  memory: MemoryPanel,
};

function PanelLoader() {
  return (
    <div className="flex h-full items-center justify-center">
      <Loading size="lg" />
    </div>
  );
}

export function TabContent({ activeTab }: { activeTab: TabType }) {
  if (activeTab === "chat") return null;

  const Panel = panelMap[activeTab];
  if (!Panel) return null;

  return (
    <main className="flex-1 overflow-hidden">
      <div className="mx-auto max-w-3xl xl:max-w-5xl w-full h-full flex flex-col">
        <Suspense fallback={<PanelLoader />}>
          <Panel />
        </Suspense>
      </div>
    </main>
  );
}
