import { lazy, Suspense, useState, useSyncExternalStore } from "react";
import { FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  activateRightPanelByKey,
  getRightPanelSnapshot,
  subscribeRightPanels,
} from "../common/rightPanelCoordinator";

const ToolResultPanel = lazy(() =>
  import("../chat/ChatMessage/items/ToolResultPanel").then((module) => ({
    default: module.ToolResultPanel,
  })),
);
const WorkspacePanel = lazy(() =>
  import("./WorkspacePanel").then((module) => ({
    default: module.WorkspacePanel,
  })),
);
interface Props {
  sessionId: string | null;
  sandboxMode?: string | null;
  machineId?: string | null;
  workspaceSelection?: string | null;
}

export function SessionWorkspaceButton(props: Props) {
  if (!props.sessionId) return null;
  // A different conversation must never inherit an open preview or in-flight read.
  return <WorkspaceButton key={props.sessionId} {...props} />;
}

function WorkspaceButton(props: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const registryKey = `workspace-${props.sessionId}`;
  const active = useSyncExternalStore(subscribeRightPanels, () => {
    const snapshot = getRightPanelSnapshot();
    return !snapshot.collapsed && snapshot.entries.some(
      (entry) => entry.id === snapshot.activeId && entry.registryKey === registryKey,
    );
  });
  const [headerActionsTarget, setHeaderActionsTarget] =
    useState<HTMLDivElement | null>(null);
  return (
    <>
      <button
        type="button"
        title={t("workspacePanel.title")}
        aria-label={t("workspacePanel.title")}
        aria-expanded={active}
        onClick={() => {
          if (open && !active) activateRightPanelByKey(registryKey);
          else setOpen(!open);
        }}
        className="flex size-11 sm:size-8 items-center justify-center rounded-lg text-theme-text-secondary hover:bg-theme-bg-subtle aria-expanded:bg-theme-bg-subtle aria-expanded:text-theme-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
      >
        <FolderOpen size={18} />
      </button>
      {open && (
        <Suspense fallback={null}>
          <ToolResultPanel
            open={open}
            onClose={() => setOpen(false)}
            title={t("workspacePanel.title")}
            icon={<FolderOpen size={16} />}
            mobileFillViewport
            headerActions={
              <div
                ref={setHeaderActionsTarget}
                className="flex shrink-0 items-center"
              />
            }
            registryKey={registryKey}
          >
            <WorkspacePanel
              key={`${props.sandboxMode}|${props.machineId}|${props.workspaceSelection}`}
              {...props}
              headerActionsTarget={headerActionsTarget}
            />
          </ToolResultPanel>
        </Suspense>
      )}
    </>
  );
}
