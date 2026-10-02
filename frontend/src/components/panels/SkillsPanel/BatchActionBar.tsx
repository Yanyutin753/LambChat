import { useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Power, Zap, Trash2, X } from "lucide-react";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { Button, IconButton } from "../../common";
import { ConfigPanelErrorCallout } from "../ConfigPanelErrorCallout";
import { restoreOpenerFocusUnclaimed } from "../../../utils/modalDialog";

interface BatchActionBarProps {
  selectedCount: number;
  batchLoading: boolean;
  error?: string | null;
  onRetry?: () => void;
  onBatchToggle?: (enabled: boolean) => void;
  onBatchDelete?: () => void;
  onClearSelection: () => void;
}

export function BatchActionBar({
  selectedCount,
  batchLoading,
  error,
  onRetry,
  onBatchToggle,
  onBatchDelete,
  onClearSelection,
}: BatchActionBarProps) {
  const { t } = useTranslation();
  const barRef = useRef<HTMLDivElement>(null);
  const focusedAction = useRef<HTMLElement | null>(null);
  useLayoutEffect(() => {
    const action = focusedAction.current;
    if (action && !action.isConnected)
      restoreOpenerFocusUnclaimed(barRef.current, action);
  });
  useLayoutEffect(() => {
    const bar = barRef.current;
    const panel = bar?.closest("[data-batch-panel]");
    return () => {
      if (bar?.contains(document.activeElement))
        // The refreshed list may remount its search in this same commit.
        queueMicrotask(() => {
          if (panel?.isConnected)
            restoreOpenerFocusUnclaimed(
              panel.querySelector<HTMLInputElement>(
                'input[type="search"], input[type="text"]',
              ),
              bar,
            );
        });
    };
  }, []);
  const run = (action: () => void) => {
    barRef.current?.focus();
    action();
  };

  return (
    <div
      ref={barRef}
      className="resource-batch-bar panel-inset"
      role="group"
      aria-label={`${t("skills.batchSelected")} ${selectedCount}`}
      aria-busy={batchLoading}
      tabIndex={-1}
      onFocusCapture={(event) => {
        focusedAction.current = event.target as HTMLElement;
      }}
      onKeyDown={(event) => {
        if (
          event.key === "Escape" &&
          !batchLoading &&
          !event.nativeEvent.isComposing
        ) {
          event.preventDefault();
          event.stopPropagation();
          onClearSelection();
        }
      }}
    >
      {error && (
        <div className="flex min-w-0 items-center gap-2 pb-2">
          <ConfigPanelErrorCallout
            message={error}
            className="min-w-0 flex-1 !rounded-lg !p-2 !text-12"
          />
          {onRetry && (
            <Button
              size="sm"
              disabled={batchLoading}
              onClick={() => run(onRetry)}
            >
              {t("common.retry")}
            </Button>
          )}
        </div>
      )}
      <div className="resource-batch-bar__actions">
        <span className="min-w-5 text-center text-13 tabular-nums text-theme-text-secondary">
          {selectedCount}
        </span>
        <span className="resource-batch-bar__label text-12 text-theme-text-secondary">
          {t("skills.batchSelected")}
        </span>
        {batchLoading && (
          <span role="status" className="inline-flex items-center gap-2">
            <LoadingSpinner size="xs" />
            <span className="sr-only">{t("auth.processing")}</span>
          </span>
        )}
        {onBatchToggle && (
          <>
            <Button
              variant="ghost"
              size="sm"
              aria-label={t("skills.card.disable")}
              title={t("skills.card.disable")}
              leftIcon={<Power size={16} aria-hidden="true" />}
              disabled={batchLoading}
              onClick={() => run(() => onBatchToggle(false))}
            >
              <span className="resource-batch-bar__label">
                {t("skills.card.disable")}
              </span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              aria-label={t("skills.card.enable")}
              title={t("skills.card.enable")}
              leftIcon={<Zap size={16} aria-hidden="true" />}
              disabled={batchLoading}
              onClick={() => run(() => onBatchToggle(true))}
            >
              <span className="resource-batch-bar__label">
                {t("skills.card.enable")}
              </span>
            </Button>
          </>
        )}
        {onBatchDelete && (
          <Button
            variant="danger"
            size="sm"
            aria-label={t("common.delete")}
            title={t("common.delete")}
            leftIcon={<Trash2 size={16} aria-hidden="true" />}
            disabled={batchLoading}
            onClick={() => run(onBatchDelete)}
          >
            <span className="resource-batch-bar__label">
              {t("common.delete")}
            </span>
          </Button>
        )}
        <IconButton
          aria-label={t("common.clear")}
          title={t("common.clear")}
          icon={<X size={16} aria-hidden="true" />}
          size="sm"
          disabled={batchLoading}
          onClick={onClearSelection}
        />
      </div>
    </div>
  );
}
