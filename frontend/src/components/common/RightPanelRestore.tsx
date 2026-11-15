import { useEffect, useRef, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { PanelRightOpen } from "lucide-react";
import { InteractiveIcon } from "./InteractiveIcon";
import { DialogCloseButton } from "./DialogCloseButton";
import {
  activateRightPanel,
  closeRightPanel,
  getRightPanelSnapshot,
  subscribeRightPanels,
} from "./rightPanelCoordinator";
import "./rightPanelTabs.css";

export function RightPanelRestore() {
  const { t } = useTranslation();
  const { entries, activeId, collapsed } = useSyncExternalStore(
    subscribeRightPanels,
    getRightPanelSnapshot,
    getRightPanelSnapshot,
  );
  const restoreRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (collapsed) restoreRef.current?.focus({ preventScroll: true });
  }, [collapsed]);
  if (!collapsed || !activeId) return null;
  return (
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
        <span className="right-panel-restore-label">
          {t("common.panelTabs")}
        </span>
        <span className="count-badge">{Math.min(entries.length, 99)}</span>
      </button>
      <DialogCloseButton
        aria-label={t("common.closeAllPanelTabs")}
        title={t("common.closeAllPanelTabs")}
        onClick={() => entries.forEach((entry) => closeRightPanel(entry.id))}
      />
    </div>
  );
}
