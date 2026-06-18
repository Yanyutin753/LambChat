import { useState, useCallback, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useRevealedFilesGrouped } from "../../hooks/useRevealedFiles";
import { getFullUrl } from "../../services/api";
import type { RevealedFileItem } from "../../services/api";
import { projectApi } from "../../services/api/project";
import DocumentPreview from "../documents/DocumentPreview";
import { ImageViewer, VideoViewer } from "../common";
import { DelayedUnmount } from "../common/DelayedUnmount";
import {
  getFileExtension,
  isExcalidrawFile,
  isVideoFile,
} from "../documents/utils";
import { ExcalidrawDirectViewer } from "../documents/previews/ExcalidrawDirectViewer";
import { Toolbar } from "./components/Toolbar";
import { SessionGroup } from "./components/SessionGroup";
import { EmptyState } from "./components/EmptyState";
import type { SortOrder, ViewMode } from "./types";
import {
  getImagePreviewNavigation,
  getPreviewableImageFiles,
  isPreviewableImageFile,
} from "./utils";
import {
  buildExternalNavigationStateForFile,
  type ExternalNavigationState,
} from "../layout/AppContent/externalNavigationState";
import type { PluginRuntimeContributionStates } from "../../extensions/coreContributions";
import { hasFileViewerContribution } from "../../extensions/coreContributions";
import { hasPluginAssetSlot } from "../../extensions/pluginAssetSlots";

export function RevealedFilesPanel({
  runtimePlugins,
}: {
  runtimePlugins?: PluginRuntimeContributionStates;
}) {
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
  const [imageViewerFile, setImageViewerFile] =
    useState<RevealedFileItem | null>(null);
  const [videoViewerSrc, setVideoViewerSrc] = useState<string | null>(null);
  const [excalidrawViewerFile, setExcalidrawViewerFile] =
    useState<RevealedFileItem | null>(null);

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
  const previewableImageFiles = useMemo(
    () => getPreviewableImageFiles(sessionGroups),
    [sessionGroups],
  );
  const imagePreviewNavigation = useMemo(
    () => getImagePreviewNavigation(previewableImageFiles, imageViewerFile?.id),
    [imageViewerFile?.id, previewableImageFiles],
  );
  const activeImageFile = imagePreviewNavigation.current ?? imageViewerFile;
  const imageViewerSrc = activeImageFile?.url
    ? getFullUrl(activeImageFile.url) ?? activeImageFile.url
    : null;
  const imageViewerPosition =
    imagePreviewNavigation.index >= 0 && imagePreviewNavigation.total > 1
      ? `${imagePreviewNavigation.index + 1} / ${imagePreviewNavigation.total}`
      : undefined;
  const advancedFileViewersEnabled =
    runtimePlugins === undefined ||
    (hasFileViewerContribution("code", runtimePlugins) &&
      hasPluginAssetSlot("file_viewer", runtimePlugins));

  /* ── Handlers ── */
  const handlePreview = useCallback(
    (file: RevealedFileItem) => {
      if (file.file_type === "project") {
        navigate(`/chat/${file.session_id}`, {
          state: buildFileNavigationState(file),
        });
        return;
      }
      const ext = getFileExtension(file.file_name);
      if (isPreviewableImageFile(file)) {
        setImageViewerFile(file);
        return;
      }
      if (file.url && (file.file_type === "video" || isVideoFile(ext))) {
        setVideoViewerSrc(getFullUrl(file.url) ?? file.url);
        return;
      }
      if (advancedFileViewersEnabled && file.url && isExcalidrawFile(ext)) {
        setExcalidrawViewerFile(file);
        return;
      }
      setPreviewFile(file);
    },
    [advancedFileViewersEnabled, buildFileNavigationState, navigate],
  );
  const handleGoToSession = useCallback(
    (sessionId: string, file?: RevealedFileItem) =>
      navigate(`/chat/${sessionId}`, {
        state: file ? buildFileNavigationState(file) : null,
      }),
    [buildFileNavigationState, navigate],
  );
  const handlePreviewClose = useCallback(() => setPreviewFile(null), []);
  const handleImageViewerClose = useCallback(
    () => setImageViewerFile(null),
    [],
  );
  const handlePreviousImage = useCallback(() => {
    if (imagePreviewNavigation.previous) {
      setImageViewerFile(imagePreviewNavigation.previous);
    }
  }, [imagePreviewNavigation.previous]);
  const handleNextImage = useCallback(() => {
    if (imagePreviewNavigation.next) {
      setImageViewerFile(imagePreviewNavigation.next);
    }
  }, [imagePreviewNavigation.next]);
  const handleVideoViewerClose = useCallback(() => setVideoViewerSrc(null), []);
  const handleExcalidrawViewerClose = useCallback(
    () => setExcalidrawViewerFile(null),
    [],
  );

  return (
    <>
      <div className="flex min-h-full flex-col @container">
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
        <div className="flex-1 overflow-y-auto min-h-0 relative z-[1] flex flex-col">
          <EmptyState
            isLoading={isLoading}
            hasFiles={sessionGroups.length > 0}
            hasActiveFilters={!!(search || selectedProject)}
          />

          {sessionGroups.length > 0 && (
            <div className="flex flex-col pb-6 px-4 @md:px-6 gap-3">
              <div className="w-full flex flex-col gap-3 @md:gap-6">
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
                      <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-stone-500 dark:border-t-stone-400 animate-spin will-change-transform" />
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
            fileSize={previewFile.file_size}
            mimeType={previewFile.mime_type ?? undefined}
            onClose={handlePreviewClose}
            mobileFillViewport
            runtimePlugins={runtimePlugins}
          />
        )}
      </DelayedUnmount>

      {/* Image fullscreen viewer */}
      {imageViewerSrc && (
        <ImageViewer
          src={imageViewerSrc}
          alt={activeImageFile?.file_name || ""}
          isOpen={!!imageViewerSrc}
          onClose={handleImageViewerClose}
          onPrevious={handlePreviousImage}
          onNext={handleNextImage}
          hasPrevious={!!imagePreviewNavigation.previous}
          hasNext={!!imagePreviewNavigation.next}
          positionLabel={imageViewerPosition}
        />
      )}

      {/* Video fullscreen viewer */}
      {videoViewerSrc && (
        <VideoViewer
          src={videoViewerSrc}
          isOpen={!!videoViewerSrc}
          onClose={handleVideoViewerClose}
          title={previewFile?.file_name || undefined}
        />
      )}

      {/* Excalidraw fullscreen viewer */}
      {excalidrawViewerFile?.url && (
        <ExcalidrawDirectViewer
          url={excalidrawViewerFile.url}
          onClose={handleExcalidrawViewerClose}
        />
      )}
    </>
  );
}
