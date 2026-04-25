import { useTranslation } from "react-i18next";
import { Power, Zap, Trash2, X } from "lucide-react";
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
    <div className="fixed bottom-4 left-4 right-4 z-40 flex justify-center sm:bottom-6 sm:left-1/2 sm:right-auto sm:-translate-x-1/2">
      <div className="flex items-center gap-1 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)]/90 px-2 py-1.5 shadow-xl shadow-black/8 dark:shadow-black/24">
        <span className="mr-1.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--theme-primary)] px-1 text-[10px] font-bold leading-none text-white">
          {selectedCount}
        </span>
        <span className="mr-1 text-xs text-[var(--theme-text-secondary)] hidden sm:inline">
          {t("skills.batchSelected")}
        </span>
        <div className="w-px h-4 bg-[var(--theme-border)]" />
        <button
          onClick={() => onBatchToggle(false)}
          disabled={batchLoading}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-medium text-[var(--theme-text-secondary)] transition-colors hover:bg-[var(--theme-hover)] hover:text-[var(--theme-text)] disabled:opacity-40 disabled:pointer-events-none"
        >
          <Power size={13} />
          <span className="hidden sm:inline">{t("skills.card.disable")}</span>
        </button>
        <button
          onClick={() => onBatchToggle(true)}
          disabled={batchLoading}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-medium text-[var(--theme-text-secondary)] transition-colors hover:bg-[var(--theme-hover)] hover:text-[var(--theme-text)] disabled:opacity-40 disabled:pointer-events-none"
        >
          <Zap size={13} />
          <span className="hidden sm:inline">{t("skills.card.enable")}</span>
        </button>
        <button
          onClick={onBatchDelete}
          disabled={batchLoading}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-medium text-red-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40 disabled:pointer-events-none dark:text-red-400 dark:hover:bg-red-950/40 dark:hover:text-red-300"
        >
          {batchLoading ? <LoadingSpinner size="xs" /> : <Trash2 size={13} />}
          <span className="hidden sm:inline">{t("common.delete")}</span>
        </button>
        <button
          onClick={onClearSelection}
          className="inline-flex items-center justify-center w-6 h-6 rounded-lg text-[var(--theme-text-tertiary)] transition-colors hover:bg-[var(--theme-hover)] hover:text-[var(--theme-text-secondary)]"
        >
          <X size={13} />
        </button>
      </div>
    </div>
  );
}
