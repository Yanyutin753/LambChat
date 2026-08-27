import { useTranslation } from "react-i18next";
import { FolderSearch, Search } from "lucide-react";
import { FilesListSkeleton } from "../../skeletons";

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

  /* Loading skeleton — real Toolbar stays mounted, so only the list is skeletonized */
  if (isLoading) {
    return <FilesListSkeleton />;
  }

  /* Empty states */
  if (!hasFiles) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 gap-5">
        {/* Illustration */}
        <div className="relative">
          <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-theme-bg-subtle to-theme-bg dark:from-theme-bg-subtle dark:to-theme-bg flex items-center justify-center border border-theme-border">
            <FolderSearch
              size={32}
              strokeWidth={1.5}
              className="text-theme-text-tertiary"
            />
          </div>
          <div className="absolute -bottom-1.5 -right-1.5 w-7 h-7 rounded-lg bg-theme-bg-elevated flex items-center justify-center ring-4 ring-theme-bg shadow-sm border border-theme-border-subtle">
            <Search size={12} className="text-theme-text-tertiary" />
          </div>
        </div>

        {/* Text */}
        <div className="text-center space-y-1.5">
          <p className="text-[14px] font-medium text-theme-text-secondary">
            {hasActiveFilters
              ? t("fileLibrary.noResults")
              : t("fileLibrary.empty")}
          </p>
          {hasActiveFilters && (
            <p className="text-[12px] text-theme-text-tertiary">
              {t("fileLibrary.tryDifferent")}
            </p>
          )}
        </div>
      </div>
    );
  }

  return null;
}
