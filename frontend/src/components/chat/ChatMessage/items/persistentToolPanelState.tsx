/* eslint-disable react-refresh/only-export-components */
import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { CollapsibleStatus } from "../../../common/CollapsiblePill";
import { isMobileDevice } from "../../../../utils/mobile";
import { ToolResultPanel } from "./ToolResultPanel";
import { closeCurrentToolPanel } from "./toolPanelRegistry";
import { createSingletonStore } from "./createSingletonStore";

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
  /** If true, skip opening on mobile devices */
  auto?: boolean;
}

const panelStore = createSingletonStore<PersistentToolPanelState | null>(null);
let panelOpen = false;

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
  if (panel.auto && isMobileDevice()) return;
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

export function PersistentToolPanelHost() {
  const { panel, close } = usePersistentToolPanel();

  if (!panel) return null;

  return createPortal(
    <ToolResultPanel
      open={true}
      onClose={close}
      registryKey={`persistent:${panel.panelKey ?? panel.title}`}
      title={panel.title}
      icon={panel.icon}
      status={panel.status}
      subtitle={panel.subtitle}
      viewMode={panel.viewMode}
      headerActions={panel.headerActions}
      customHeader={panel.customHeader}
      footer={panel.footer}
      overlayClass={panel.overlayClass}
      panelClass={panel.panelClass}
      onUserInteraction={panel.onUserInteraction}
    >
      {panel.children}
    </ToolResultPanel>,
    document.body,
  );
}
