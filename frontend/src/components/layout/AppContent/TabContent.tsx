import { Suspense, lazy } from "react";
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
const PersonaPlazaPanel = lazy(() =>
  import("../../persona/PersonaPlazaPanel").then((m) => ({
    default: m.PersonaPlazaPanel,
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
  agents: AgentConfigPanel,
  models: ModelPanel,
  files: RevealedFilesPage,
  persona: PersonaPlazaPanel,
  notifications: NotificationPanel,
  memory: MemoryPanel,
};

function PanelLoader() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="relative h-8 w-8">
        <div className="absolute inset-0 rounded-full border-2 border-stone-200 dark:border-stone-700" />
        <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-stone-500 dark:border-t-stone-400 animate-spin will-change-transform" />
      </div>
    </div>
  );
}

export function TabContent({ activeTab }: { activeTab: TabType }) {
  if (activeTab === "chat") return null;

  const Panel = panelMap[activeTab];
  if (!Panel) return null;

  return (
    <main className="flex-1 overflow-hidden">
      <div className="mx-auto max-w-3xl sm:max-w-6xl w-full h-full flex flex-col">
        <Suspense fallback={<PanelLoader />}>
          <Panel />
        </Suspense>
      </div>
    </main>
  );
}
