import { useTranslation } from "react-i18next";
import { Power, Zap, Trash2, X } from "lucide-react";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { Button, IconButton } from "../../common";

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
      <div className="flex items-center gap-1 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 py-1.5 shadow-xl shadow-black/8 dark:shadow-black/24">
        <span className="mr-1.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--theme-primary)] px-1 text-10 font-bold leading-none text-white dark:text-[var(--theme-bg)]">
          {selectedCount}
        </span>
        <span className="mr-1 text-xs text-[var(--theme-text-secondary)] hidden sm:inline">
          {t("skills.batchSelected")}
        </span>
        <div className="w-px h-4 bg-[var(--theme-border)]" />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onBatchToggle(false)}
          disabled={batchLoading}
          className="text-xs text-[var(--theme-text-secondary)] hover:bg-[var(--theme-hover)] disabled:pointer-events-none disabled:opacity-40"
        >
          <Power size={13} />
          <span className="hidden sm:inline">{t("skills.card.disable")}</span>
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onBatchToggle(true)}
          disabled={batchLoading}
          className="text-xs text-[var(--theme-text-secondary)] hover:bg-[var(--theme-hover)] disabled:pointer-events-none disabled:opacity-40"
        >
          <Zap size={13} />
          <span className="hidden sm:inline">{t("skills.card.enable")}</span>
        </Button>
        <Button
          variant="danger"
          size="sm"
          onClick={onBatchDelete}
          disabled={batchLoading}
          className="text-xs disabled:pointer-events-none disabled:opacity-40 dark:text-red-400 dark:hover:bg-red-950/40 dark:hover:text-red-300"
        >
          {batchLoading ? <LoadingSpinner size="xs" /> : <Trash2 size={13} />}
          <span className="hidden sm:inline">{t("common.delete")}</span>
        </Button>
        <IconButton
          aria-label={t("common.clear")}
          icon={<X size={13} />}
          size="sm"
          onClick={onClearSelection}
          className="h-6 w-6 text-[var(--theme-text-tertiary)] hover:bg-[var(--theme-hover)] hover:text-[var(--theme-text-secondary)]"
        />
      </div>
    </div>
  );
}
