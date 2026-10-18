import { InteractiveIcon } from "./InteractiveIcon";
import { useEffect, useRef, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import "./rightPanelTabs.css";
import { Tooltip } from "./Tooltip";
import { DialogCloseButton } from "./DialogCloseButton";
import {
  Columns2,
  Expand,
  Shrink,
  PanelRight,
  PanelRightClose,
  PanelRightOpen,
  X,
} from "lucide-react";
import { RightPanelTabPreview } from "./RightPanelTabPreview";
import { useTranslation } from "react-i18next";
import {
  activateRightPanel,
  closeRightPanel,
  collapseRightPanel,
  getRightPanelSnapshot,
  subscribeRightPanels,
} from "./rightPanelCoordinator";

/** Shared strip for editor, tool, and document panels. */
export function RightPanelTabs({
  viewControls,
}: {
  viewControls?: {
    isSidebar: boolean;
    isFullscreen: boolean;
    onToggleViewMode: () => void;
    onToggleFullscreen: () => void;
  };
} = {}) {
  const { t } = useTranslation();
  const { entries, activeId, collapsed } = useSyncExternalStore(
    subscribeRightPanels,
    getRightPanelSnapshot,
    getRightPanelSnapshot,
  );

  const restoreRef = useRef<HTMLButtonElement>(null);
  const tabsRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const tabs = tabsRef.current;
    if (!tabs) return;
    const revealSelected = () => {
      if (window.innerWidth >= 640) return;
      tabs
        .querySelector<HTMLElement>('[role="tab"][aria-selected="true"]')
        ?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    };
    revealSelected();
    if (typeof ResizeObserver === "undefined" || !tabs.parentElement) return;
    const observer = new ResizeObserver(revealSelected);
    observer.observe(tabs.parentElement);
    return () => observer.disconnect();
  }, [activeId, collapsed]);
  useEffect(() => {
    if (collapsed) restoreRef.current?.focus({ preventScroll: true });
  }, [collapsed]);

  if (collapsed && activeId) {
    return createPortal(
      <div
        className="right-panel-restore-group"
        role="group"
        aria-label={t("common.panelTabs")}
      >
        <button
          ref={restoreRef}
          type="button"
          className="right-panel-restore"
          onClick={() => activateRightPanel(activeId)}
          aria-label={t("common.expandPanel")}
          title={t("common.expandPanel")}
          aria-expanded={false}
        >
          <InteractiveIcon>
            <PanelRightOpen size={16} aria-hidden="true" />
          </InteractiveIcon>
          <span>{t("common.panelTabs")}</span>
          <span className="count-badge">{Math.min(entries.length, 99)}</span>
        </button>
        <DialogCloseButton
          aria-label={t("common.closeAllPanelTabs")}
          title={t("common.closeAllPanelTabs")}
          onClick={() => entries.forEach((entry) => closeRightPanel(entry.id))}
        />
      </div>,
      document.body,
    );
  }

  return (
    <div className="right-panel-tabbar">
      <div className="right-panel-tab-scroll">
        <div
          role="tablist"
          ref={tabsRef}
          aria-label={t("common.panelTabs")}
          className="right-panel-tabs"
        >
          {entries.map((entry, index) => {
            const selected = entry.id === activeId;
            const label = entry.title || t("documents.preview");
            return (
              <div
                key={entry.panelId ?? index}
                role="presentation"
                className="right-panel-tab"
                data-selected={selected}
              >
                <Tooltip
                  placement="bottom"
                  hoverDelay={500}
                  zIndex={300}
                  portalContainer={document.fullscreenElement ?? undefined}
                  className="right-panel-tab-tooltip"
                  content={<RightPanelTabPreview entry={entry} label={label} />}
                >
                  <button
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    aria-controls={entry.panelId}
                    tabIndex={selected ? 0 : -1}
                    onClick={() => activateRightPanel(entry.id)}
                    onKeyDown={(event) => {
                      let next: number;
                      if (event.key === "ArrowRight")
                        next = (index + 1) % entries.length;
                      else if (event.key === "ArrowLeft")
                        next = (index + entries.length - 1) % entries.length;
                      else if (event.key === "Home") next = 0;
                      else if (event.key === "End") next = entries.length - 1;
                      else if (event.key === "Delete") {
                        event.preventDefault();
                        closeRightPanel(entry.id);
                        return;
                      } else return;
                      event.preventDefault();
                      activateRightPanel(entries[next].id);
                    }}
                  >
                    <span className="right-panel-tab-icon" aria-hidden="true">
                      {entry.icon ?? (
                        <InteractiveIcon>
                          <PanelRight size={14} />
                        </InteractiveIcon>
                      )}
                    </span>
                    <span className="right-panel-tab-label">{label}</span>
                  </button>
                </Tooltip>
                <button
                  type="button"
                  className="right-panel-tab-close"
                  tabIndex={selected ? 0 : -1}
                  aria-label={t("common.closePanelTab", { title: label })}
                  title={t("common.closePanelTab", { title: label })}
                  onClick={() => closeRightPanel(entry.id)}
                >
                  <InteractiveIcon>
                    <X size={16} aria-hidden="true" />
                  </InteractiveIcon>
                </button>
              </div>
            );
          })}
        </div>
        <div className="right-panel-tab-actions right-panel-secondary-actions">
          {viewControls && (
            <>
              <button
                type="button"
                className="right-panel-view-action"
                aria-pressed={!viewControls.isSidebar}
                aria-label={t(
                  viewControls.isSidebar
                    ? "documents.centerView"
                    : "documents.sidebarView",
                )}
                title={t(
                  viewControls.isSidebar
                    ? "documents.centerView"
                    : "documents.sidebarView",
                )}
                onClick={viewControls.onToggleViewMode}
              >
                {viewControls.isSidebar ? (
                  <InteractiveIcon>
                    <Columns2 size={16} aria-hidden="true" />
                  </InteractiveIcon>
                ) : (
                  <InteractiveIcon>
                    <PanelRight size={16} aria-hidden="true" />
                  </InteractiveIcon>
                )}
              </button>
              <button
                type="button"
                className="right-panel-view-action"
                aria-label={t(
                  viewControls.isFullscreen
                    ? "documents.exitFullscreen"
                    : "documents.fullscreen",
                )}
                title={t(
                  viewControls.isFullscreen
                    ? "documents.exitFullscreen"
                    : "documents.fullscreen",
                )}
                onClick={viewControls.onToggleFullscreen}
              >
                {viewControls.isFullscreen ? (
                  <InteractiveIcon>
                    <Shrink size={16} aria-hidden="true" />
                  </InteractiveIcon>
                ) : (
                  <InteractiveIcon>
                    <Expand size={16} aria-hidden="true" />
                  </InteractiveIcon>
                )}
              </button>
            </>
          )}
        </div>
      </div>
      <div className="right-panel-tab-actions">
        <button
          type="button"
          className="right-panel-collapse"
          onClick={collapseRightPanel}
          aria-label={t("common.collapsePanel")}
          title={t("common.collapsePanel")}
          aria-expanded={true}
        >
          <InteractiveIcon>
            <PanelRightClose size={16} aria-hidden="true" />
          </InteractiveIcon>
        </button>
      </div>
    </div>
  );
}
