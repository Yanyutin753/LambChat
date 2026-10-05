import { FolderSearch } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Button, EmptyState as PanelEmptyState } from "../../common";
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
  const navigate = useNavigate();

  /* Loading skeleton — real Toolbar stays mounted, so only the list is skeletonized */
  if (isLoading) {
    return <FilesListSkeleton />;
  }

  /* Empty states */
  if (!hasFiles) {
    return (
      <PanelEmptyState
        className="flex-1"
        icon={<FolderSearch size={20} />}
        title={
          hasActiveFilters ? t("fileLibrary.noResults") : t("fileLibrary.empty")
        }
        description={
          hasActiveFilters ? t("fileLibrary.tryDifferent") : undefined
        }
        action={
          !hasActiveFilters ? (
            <Button variant="primary" onClick={() => navigate("/chat")}>
              {t("fileLibrary.emptyAction")}
            </Button>
          ) : undefined
        }
      />
    );
  }

  return null;
}
