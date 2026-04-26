import { useState, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useRevealedFilesGrouped } from "../../hooks/useRevealedFiles";
import { getFullUrl } from "../../services/api";
import type { RevealedFileItem } from "../../services/api";
import { projectApi } from "../../services/api/project";
import DocumentPreview from "../documents/DocumentPreview";
import { DelayedUnmount } from "../common/DelayedUnmount";
import { Toolbar } from "./components/Toolbar";
import { SessionGroup } from "./components/SessionGroup";
import { EmptyState } from "./components/EmptyState";
import type { SortOrder, ViewMode } from "./types";
import {
  buildExternalNavigationStateForFile,
  type ExternalNavigationState,
} from "../layout/AppContent/externalNavigationState";

export function RevealedFilesPanel() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  /* ── State ── */
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [projects, setProjects] = useState<
    Array<{ id: string; name: string; type: string }>
  >([]);
  const [previewFile, setPreviewFile] = useState<RevealedFileItem | null>(null);

  /* ── Data ── */
  useEffect(() => {
    let cancelled = false;
    projectApi
      .list()
      .then((data) => {
        if (!cancelled) setProjects(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const {
    sessionGroups,
    isLoading,
    isLoadingMore,
    hasMore,
    loadMoreRef,
    toggleFavorite,
  } = useRevealedFilesGrouped({
    search: search || undefined,
    file_type: activeFilter === "all" ? undefined : activeFilter,
    project_id: selectedProject || undefined,
    favorites_only: favoritesOnly || undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
  });

  const buildFileNavigationState = useCallback(
    (file: RevealedFileItem): ExternalNavigationState =>
      buildExternalNavigationStateForFile(file),
    [],
  );

  /* ── Handlers ── */
  const handlePreview = useCallback(
    (file: RevealedFileItem) => {
      if (file.file_type === "project") {
        navigate(`/chat/${file.session_id}`, {
          state: buildFileNavigationState(file),
        });
        return;
      }
      setPreviewFile(file);
    },
    [buildFileNavigationState, navigate],
  );
  const handleGoToSession = useCallback(
    (sessionId: string, file?: RevealedFileItem) =>
      navigate(`/chat/${sessionId}`, {
        state: file ? buildFileNavigationState(file) : null,
      }),
    [buildFileNavigationState, navigate],
  );
  const handlePreviewClose = useCallback(() => setPreviewFile(null), []);

  return (
    <>
      <div className="flex min-h-full flex-col">
        {/* Toolbar */}
        <Toolbar
          search={search}
          onSearchChange={setSearch}
          activeFilter={activeFilter}
          onFilterChange={setActiveFilter}
          sortBy={sortBy}
          sortOrder={sortOrder}
          onSortChange={(key, order) => {
            setSortBy(key);
            setSortOrder(order);
          }}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          favoritesOnly={favoritesOnly}
          onFavoritesToggle={() => setFavoritesOnly((v) => !v)}
          projects={projects}
          selectedProject={selectedProject}
          onProjectChange={setSelectedProject}
        />

        {/* Content area */}
        <div className="flex-1 overflow-y-auto min-h-0 relative z-[1]">
          <EmptyState
            isLoading={isLoading}
            hasFiles={sessionGroups.length > 0}
            hasActiveFilters={!!(search || selectedProject)}
          />

          {sessionGroups.length > 0 && (
            <div className="flex flex-col pb-6 px-5 md:px-6 gap-3">
              <div className="w-full flex flex-col gap-3 md:gap-6">
                {sessionGroups.map((group) => (
                  <SessionGroup
                    key={group.session_id}
                    sessionName={
                      group.session_name || t("fileLibrary.untitledSession")
                    }
                    sessionId={group.session_id}
                    files={group.files}
                    onPreview={handlePreview}
                    onGoToSession={handleGoToSession}
                    onToggleFavorite={(f) => toggleFavorite(f.id)}
                    viewMode={viewMode}
                  />
                ))}
              </div>

              {/* Load more */}
              {hasMore && (
                <div
                  ref={loadMoreRef}
                  className="flex items-center justify-center py-8"
                >
                  {isLoadingMore && (
                    <div className="relative w-5 h-5">
                      <div className="absolute inset-0 rounded-full border-2 border-stone-200 dark:border-stone-700" />
                      <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-stone-500 dark:border-t-stone-400 animate-spin" />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Document preview modal */}
      <DelayedUnmount show={!!previewFile}>
        {previewFile && (
          <DocumentPreview
            path={previewFile.file_name}
            signedUrl={
              previewFile.url ? getFullUrl(previewFile.url) : undefined
            }
            imageUrl={
              previewFile.file_type === "image" && previewFile.url
                ? getFullUrl(previewFile.url)
                : undefined
            }
            fileSize={previewFile.file_size}
            onClose={handlePreviewClose}
          />
        )}
      </DelayedUnmount>
    </>
  );
}
