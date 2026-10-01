import { useSyncExternalStore } from "react";
import "./rightPanelTabs.css";
import { PanelRight, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  activateRightPanel,
  closeRightPanel,
  getRightPanelSnapshot,
  subscribeRightPanels,
} from "./rightPanelCoordinator";

/** Shared strip for editor, tool, and document panels. */
export function RightPanelTabs() {
  const { t } = useTranslation();
  const { entries, activeId } = useSyncExternalStore(
    subscribeRightPanels,
    getRightPanelSnapshot,
    getRightPanelSnapshot,
  );

  return (
    <div
      role="tablist"
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
            <button
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={entry.panelId}
              tabIndex={selected ? 0 : -1}
              title={label}
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
                {entry.icon ?? <PanelRight size={14} />}
              </span>
              <span className="right-panel-tab-label">{label}</span>
            </button>
            <button
              type="button"
              className="right-panel-tab-close"
              tabIndex={selected ? 0 : -1}
              aria-label={t("common.closePanelTab", { title: label })}
              title={t("common.closePanelTab", { title: label })}
              onClick={() => closeRightPanel(entry.id)}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
