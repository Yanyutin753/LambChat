/* eslint-disable react-refresh/only-export-components */
import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { CollapsibleStatus } from "../../../common/CollapsiblePill";
import { hasOpenRightPanel } from "../../../common/rightPanelCoordinator";
import {
  getRightPanelPresentation,
  shouldAllowAutomaticRightPanel,
} from "../../../../hooks/rightPanelLayout";
import { ToolResultPanel } from "./ToolResultPanel";
import { closeCurrentToolPanel } from "./toolPanelRegistry";
import { createSingletonStore } from "./createSingletonStore";
import { setActiveRevealPreviewState } from "./activeRevealPreviewStore";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { toolCallPanelStore } from "../toolCallPanelStore";
import {
  buildSubagentPanelState,
  createSubagentPanelFooter,
} from "../subagentPanelState";
import { subagentPanelStore } from "../subagentPanelStore";
import {
  registerPanelCapture,
  pushCurrentPanelToHistory,
} from "./sidebarHistoryStore";

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
}

const panelStore = createSingletonStore<PersistentToolPanelState | null>(null);
let panelOpen = false;

registerPanelCapture(() => {
  const panel = panelStore.get();
  if (panel) {
    const captured = panel;
    return {
      restore: () => {
        setActiveRevealPreviewState(null);
        openPersistentToolPanelDirect(captured);
      },
    };
  }
  return null;
});

function openPersistentToolPanelDirect(panel: PersistentToolPanelState): void {
  panelStore.set(panel);
  panelOpen = true;
}

export function getPersistentToolPanelState(): PersistentToolPanelState | null {
  return panelStore.get();
}

export function subscribePersistentToolPanel(listener: () => void): () => void {
  return panelStore.subscribe(listener);
}

export function isPersistentToolPanelOpen(panelKey?: string): boolean {
  const currentPanel = panelStore.get();
  if (!panelKey) return panelOpen;
  return !!currentPanel && currentPanel.panelKey === panelKey;
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
  pushCurrentPanelToHistory();
  closeCurrentToolPanel();
  panelStore.set(panel);
  panelOpen = true;
}

export function updatePersistentToolPanel(
  updater: (prev: PersistentToolPanelState) => PersistentToolPanelState,
  panelKey?: string,
): void {
  const currentPanel = panelStore.get();
  if (!currentPanel) return;
  if (panelKey && currentPanel.panelKey !== panelKey) return;
  panelStore.set(updater(currentPanel));
}

export function closePersistentToolPanel(): void {
  if (!panelStore.get()) return;
  panelStore.set(null);
  panelOpen = false;
}

function usePersistentToolPanel() {
  const [, forceRender] = useState(0);

  useEffect(() => {
    const listener = () => forceRender((count) => count + 1);
    return subscribePersistentToolPanel(listener);
  }, []);

  return {
    panel: panelStore.get(),
    close: closePersistentToolPanel,
  };
}

interface LivePanelChrome {
  status: CollapsibleStatus;
  footer?: ReactNode;
}

/**
 * 面板头部状态与页脚的实时数据源：tool: 前缀走 toolCallPanelStore，
 * subagent- 前缀走 subagentPanelStore。两个 store 均由 ChatView 全量
 * 同步，面板刷新与消息虚拟化（滚动）无关。
 */
function useLivePanelChrome(panelKey?: string): LivePanelChrome | null {
  const toolCallId = panelKey?.startsWith("tool:")
    ? panelKey.slice("tool:".length)
    : null;
  const subagentId = panelKey?.startsWith("subagent-")
    ? panelKey.slice("subagent-".length)
    : null;
  const [, forceRender] = useState(0);

  useEffect(() => {
    const listener = () => forceRender((count) => count + 1);
    if (toolCallId) return toolCallPanelStore.subscribe(toolCallId, listener);
    if (subagentId) return subagentPanelStore.subscribe(subagentId, listener);
  }, [toolCallId, subagentId]);

  const toolData = toolCallId
    ? toolCallPanelStore.get(toolCallId)
    : undefined;
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
      footer: createSubagentPanelFooter(subtitle),
    };
  }

  return null;
}

export function PersistentToolPanelHost() {
  const { panel, close } = usePersistentToolPanel();
  const liveChrome = useLivePanelChrome(panel?.panelKey);

  if (!panel) return null;

  return createPortal(
    <ToolResultPanel
      open={true}
      onClose={close}
      registryKey={`persistent:${panel.panelKey ?? panel.title}`}
      automatic={panel.auto}
      title={panel.title}
      icon={panel.icon}
      status={liveChrome?.status ?? panel.status}
      subtitle={panel.subtitle}
      viewMode={panel.viewMode}
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
}
