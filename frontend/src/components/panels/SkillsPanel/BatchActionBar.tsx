import { useTranslation } from "react-i18next";
import { ToggleLeft, ToggleRight, Trash2, X } from "lucide-react";
import { LoadingSpinner } from "../../common/LoadingSpinner";

interface BatchActionBarProps {
  selectedCount: number;
  batchLoading: boolean;
  onBatchToggle: (enabled: boolean) => void;
  onBatchDelete: () => void;
  onClearSelection: () => void;
}

export function BatchActionBar({
  selectedCount,
  batchLoading,
  onBatchToggle,
  onBatchDelete,
  onClearSelection,
}: BatchActionBarProps) {
  const { t } = useTranslation();

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-stone-200 bg-white/95 px-4 py-3 shadow-lg dark:border-stone-800 dark:bg-stone-900/95 sm:left-auto sm:right-auto sm:mx-auto sm:max-w-3xl sm:rounded-t-2xl">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-[var(--theme-text)]">
          <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-[var(--theme-primary)] px-1.5 text-[11px] font-bold text-white">
            {selectedCount}
          </span>
          <span className="text-[var(--theme-text-secondary)]">
            {t("skills.batchSelected")}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onBatchToggle(false)}
            disabled={batchLoading}
            className="btn-secondary text-xs"
          >
            <ToggleLeft size={14} />
            <span className="hidden sm:inline">{t("skills.card.disable")}</span>
          </button>
          <button
            onClick={() => onBatchToggle(true)}
            disabled={batchLoading}
            className="btn-secondary text-xs"
          >
            <ToggleRight size={14} />
            <span className="hidden sm:inline">{t("skills.card.enable")}</span>
          </button>
          <button
            onClick={onBatchDelete}
            disabled={batchLoading}
            className="inline-flex items-center gap-1.5 rounded-xl bg-red-50 px-3 py-2 text-xs font-medium text-red-600 transition-colors hover:bg-red-100 dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50 disabled:opacity-50"
          >
            {batchLoading ? (
              <LoadingSpinner
                size="sm"
                color="text-red-600 dark:text-red-400"
              />
            ) : (
              <Trash2 size={14} />
            )}
            <span className="hidden sm:inline">{t("common.delete")}</span>
          </button>
          <button onClick={onClearSelection} className="btn-secondary text-xs">
            <X size={14} />
            <span className="hidden sm:inline">{t("common.cancel")}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
