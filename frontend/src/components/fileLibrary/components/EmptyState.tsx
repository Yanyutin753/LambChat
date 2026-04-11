import { useTranslation } from "react-i18next";
import { FolderSearch, Search } from "lucide-react";

interface EmptyStateProps {
  isLoading: boolean;
  hasFiles: boolean;
  hasActiveFilters: boolean;
}

export function EmptyState({
  isLoading,
  hasFiles,
  hasActiveFilters,
}: EmptyStateProps) {
  const { t } = useTranslation();

  /* Loading spinner */
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-72">
        <div className="flex flex-col items-center gap-3">
          <div className="relative w-8 h-8">
            <div className="absolute inset-0 rounded-full border-2 border-stone-200 dark:border-stone-700" />
            <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-stone-500 dark:border-t-stone-400 animate-spin" />
          </div>
          <p className="text-[13px] text-stone-400 dark:text-stone-500">
            {t("fileLibrary.loading")}
          </p>
        </div>
      </div>
    );
  }

  /* Empty states */
  if (!hasFiles) {
    return (
      <div className="flex flex-col items-center justify-center h-72 gap-5">
        {/* Illustration */}
        <div className="relative">
          <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-stone-100 to-stone-50 dark:from-stone-800/60 dark:to-stone-800/30 flex items-center justify-center border border-stone-200/50 dark:border-stone-700/30">
            <FolderSearch
              size={32}
              strokeWidth={1.5}
              className="text-stone-300 dark:text-stone-600"
            />
          </div>
          <div className="absolute -bottom-1.5 -right-1.5 w-7 h-7 rounded-lg bg-white dark:bg-stone-700 flex items-center justify-center ring-4 ring-stone-50 dark:ring-stone-950 shadow-sm border border-stone-100 dark:border-stone-600">
            <Search size={12} className="text-stone-400 dark:text-stone-500" />
          </div>
        </div>

        {/* Text */}
        <div className="text-center space-y-1.5">
          <p className="text-[14px] font-medium text-stone-500 dark:text-stone-400">
            {hasActiveFilters
              ? t("fileLibrary.noResults")
              : t("fileLibrary.empty")}
          </p>
          {hasActiveFilters && (
            <p className="text-[12px] text-stone-300 dark:text-stone-600">
              {t("fileLibrary.tryDifferent")}
            </p>
          )}
        </div>
      </div>
    );
  }

  return null;
}
