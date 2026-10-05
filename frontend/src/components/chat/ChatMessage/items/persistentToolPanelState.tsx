/* eslint-disable react-refresh/only-export-components */
import {
  useCallback,
  useEffect,
  useState,
  useSyncExternalStore,
  memo,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import type { CollapsibleStatus } from "../../../common/CollapsiblePill";
import {
  hasOpenRightPanel,
  getRightPanelSnapshot,
  subscribeRightPanels,
} from "../../../common/rightPanelCoordinator";
import {
  getRightPanelPresentation,
  shouldAllowAutomaticRightPanel,
} from "../../../../hooks/rightPanelLayout";
import { ToolResultPanel } from "./ToolResultPanel";
import { createPanelTabsStore } from "./createPanelTabsStore";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { toolCallPanelStore } from "../toolCallPanelStore";
import {
  buildSubagentPanelState,
  createSubagentPanelFooter,
} from "../subagentPanelState";
import { subagentPanelStore } from "../subagentPanelStore";
import { buildPanelSummary } from "../panelSummary";
export interface PersistentToolPanelState {
  title: string;
  status: CollapsibleStatus;
  children: ReactNode;
  panelKey?: string;
  icon?: ReactNode;
  subtitle?: string;
  viewMode?: "sidebar" | "center";
  headerActions?: ReactNode;
  customHeader?: ReactNode;
  footer?: ReactNode;
  overlayClass?: string;
  panelClass?: string;
  onUserInteraction?: () => void;
  onUserClose?: () => void;
  /** If true, skip opening on mobile devices */
  auto?: boolean;
  /** When true, mobile renders as full-viewport instead of bottom sheet */
  mobileFillViewport?: boolean;
  /** 用户切换过全屏时记录：面板历史返回后恢复原视图，而非重置 */
  isFullscreen?: boolean;
}

function panelRegistryKey(panel: PersistentToolPanelState): string {
  return `persistent:${panel.panelKey ?? panel.title}`;
}
const panelStore =
  createPanelTabsStore<PersistentToolPanelState>(panelRegistryKey);
export const closeAllPersistentToolPanels = panelStore.clear;

export function getPersistentToolPanelState(): PersistentToolPanelState | null {
  return panelStore.get();
}

export function subscribePersistentToolPanel(listener: () => void): () => void {
  return panelStore.subscribe(listener);
}

export function isPersistentToolPanelOpen(panelKey?: string): boolean {
  if (!panelKey) return panelStore.getAll().length > 0;
  return panelStore.getAll().some((panel) => panel.panelKey === panelKey);
}

export function isPersistentToolPanelActive(panelKey: string): boolean {
  const snapshot = getRightPanelSnapshot();
  return !snapshot.collapsed && snapshot.entries.some(
    (entry) =>
      entry.id === snapshot.activeId &&
      entry.registryKey === `persistent:${panelKey}`,
  );
}

export function openPersistentToolPanel(panel: PersistentToolPanelState): void {
  if (
    panel.auto &&
    !shouldAllowAutomaticRightPanel({
      presentation: getRightPanelPresentation(window.innerWidth),
      laneOccupied: hasOpenRightPanel(),
    })
  ) {
    return;
  }
  const existing = panelStore
    .getAll()
    .find((tab) => panelRegistryKey(tab) === panelRegistryKey(panel));
  panelStore.open(
    existing
      ? {
          ...panel,
          viewMode: existing.viewMode ?? panel.viewMode,
          isFullscreen: existing.isFullscreen ?? panel.isFullscreen,
        }
      : panel,
  );
}

export function updatePersistentToolPanel(
  updater: (prev: PersistentToolPanelState) => PersistentToolPanelState,
  panelKey?: string,
): void {
  panelStore.update(updater, panelKey ? `persistent:${panelKey}` : undefined);
}

export function closePersistentToolPanel(panelKey?: string): void {
  panelStore.close(panelKey ? `persistent:${panelKey}` : undefined);
}

interface LivePanelChrome {
  status: CollapsibleStatus;
  subtitle?: string;
  footer?: ReactNode;
}

/**
 * 面板头部状态与页脚的实时数据源：tool: 前缀走 toolCallPanelStore，
 * subagent- 前缀走 subagentPanelStore。两个 store 均由 ChatView 全量
 * 同步，面板刷新与消息虚拟化（滚动）无关。
 */
function useLivePanelChrome(
  active: boolean,
  panelKey?: string,
): LivePanelChrome | null {
  const toolCallId = panelKey?.startsWith("tool:")
    ? panelKey.slice("tool:".length)
    : null;
  const subagentId = panelKey?.startsWith("subagent-")
    ? panelKey.slice("subagent-".length)
    : null;
  const [, forceRender] = useState(0);

  useEffect(() => {
    if (!active) return;
    const listener = () => forceRender((count) => count + 1);
    if (toolCallId) return toolCallPanelStore.subscribe(toolCallId, listener);
    if (subagentId) return subagentPanelStore.subscribe(subagentId, listener);
  }, [active, toolCallId, subagentId]);

  const toolData = toolCallId ? toolCallPanelStore.get(toolCallId) : undefined;
  if (toolData) {
    return {
      status: toolData.status,
      footer: (
        <ToolDurationFooter
          startedAt={toolData.startedAt}
          completedAt={toolData.completedAt}
        />
      ),
    };
  }

  const subagentData = subagentId
    ? subagentPanelStore.get(subagentId)
    : undefined;
  if (subagentData) {
    const { panelStatus, subtitle } = buildSubagentPanelState(subagentData);
    return {
      status: panelStatus,
      subtitle: buildPanelSummary(subagentData.input),
      footer: createSubagentPanelFooter(subtitle),
    };
  }

  return null;
}

const PersistentToolPanelTab = memo(function PersistentToolPanelTab({
  panel,
}: {
  panel: PersistentToolPanelState;
}) {
  const close = useCallback(
    () => panelStore.close(panelRegistryKey(panel)),
    [panel],
  );
  const registryKey = panelRegistryKey(panel);
  const active = useSyncExternalStore(subscribeRightPanels, () => {
    const snapshot = getRightPanelSnapshot();
    return !snapshot.collapsed && snapshot.entries.some(
      (entry) =>
        entry.id === snapshot.activeId && entry.registryKey === registryKey,
    );
  });
  const liveChrome = useLivePanelChrome(active, panel.panelKey);

  // viewMode/全屏完全受控并回写 store：面板历史返回后恢复用户当时的
  // 视图模式，也修掉同一面板实例在不同面板之间串台的问题
  const activePanelKey = panel?.panelKey;
  const handleViewModeChange = useCallback(
    (mode: "sidebar" | "center") => {
      updatePersistentToolPanel(
        (prev) => ({ ...prev, viewMode: mode }),
        activePanelKey,
      );
    },
    [activePanelKey],
  );
  const handleFullscreenChange = useCallback(
    (fullscreen: boolean) => {
      updatePersistentToolPanel(
        (prev) => ({ ...prev, isFullscreen: fullscreen }),
        activePanelKey,
      );
    },
    [activePanelKey],
  );

  return createPortal(
    <ToolResultPanel
      open={true}
      onClose={close}
      registryKey={`persistent:${panel.panelKey ?? panel.title}`}
      automatic={panel.auto}
      title={panel.title}
      icon={panel.icon}
      status={liveChrome?.status ?? panel.status}
      subtitle={liveChrome?.subtitle ?? panel.subtitle}
      viewMode={panel.viewMode ?? "sidebar"}
      onViewModeChange={handleViewModeChange}
      isFullscreen={panel.isFullscreen ?? false}
      onFullscreenChange={handleFullscreenChange}
      headerActions={panel.headerActions}
      customHeader={panel.customHeader}
      footer={liveChrome?.footer ?? panel.footer}
      overlayClass={panel.overlayClass}
      panelClass={panel.panelClass}
      mobileFillViewport={panel.mobileFillViewport}
      onUserInteraction={panel.onUserInteraction}
      onUserClose={panel.onUserClose}
    >
      {panel.children}
    </ToolResultPanel>,
    document.body,
  );
});

export function PersistentToolPanelHost() {
  const panels = useSyncExternalStore(
    panelStore.subscribe,
    panelStore.getAll,
    panelStore.getAll,
  );
  return panels.map((panel) => (
    <PersistentToolPanelTab key={panelRegistryKey(panel)} panel={panel} />
  ));
}
