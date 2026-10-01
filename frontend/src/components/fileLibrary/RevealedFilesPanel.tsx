import { useState, useCallback, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useRevealedFilesGrouped } from "../../hooks/useRevealedFiles";
import { getFullUrl } from "../../services/api";
import type { RevealedFileItem } from "../../services/api";
import { projectApi } from "../../services/api/project";
import { LazyDocumentPreview as DocumentPreview } from "../documents/LazyDocumentPreview";
import { activateRightPanelByKey } from "../common/rightPanelCoordinator";
import { ImageViewer, VideoViewer } from "../common";
import {
  getFileExtension,
  isExcalidrawFile,
  isVideoFile,
} from "../documents/utils";
import { ExcalidrawDirectViewer } from "../documents/previews/ExcalidrawDirectViewer";
import { Pagination } from "../common/Pagination";
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
  const [previewFiles, setPreviewFiles] = useState<RevealedFileItem[]>([]);
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
    totalSessions,
    page,
    pageSize,
    setPage,
    error,
    refresh,
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
      if (file.url && isExcalidrawFile(ext)) {
        setExcalidrawViewerFile(file);
        return;
      }
      setPreviewFiles((current) =>
        current.some((item) => item.id === file.id)
          ? current
          : [...current, file],
      );
      activateRightPanelByKey(`library-preview:${file.id}`);
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
      <div className="flex h-full min-h-0 flex-col @container">
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
        <div className="panel-body flex-1 overflow-y-auto min-h-0 relative z-[1] flex flex-col">
          {error && (
            <div
              role="alert"
              className="p-4 text-center text-theme-text-secondary"
            >
              <p>{error}</p>
              <button
                type="button"
                className="btn-secondary mt-3"
                onClick={refresh}
              >
                {t("common.refresh")}
              </button>
            </div>
          )}
          {!error && (
            <EmptyState
              isLoading={isLoading}
              hasFiles={sessionGroups.length > 0}
              hasActiveFilters={
                !!(
                  search ||
                  selectedProject ||
                  favoritesOnly ||
                  activeFilter !== "all"
                )
              }
            />
          )}

          {sessionGroups.length > 0 && (
            <div className="panel-stack">
              <div className="panel-sections w-full">
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
            </div>
          )}
        </div>
        <div className="panel-pagination empty:hidden">
          <Pagination
            page={page}
            pageSize={pageSize}
            total={totalSessions}
            onChange={setPage}
          />
        </div>
      </div>

      {/* Document preview modal */}
      {previewFiles.map((previewFile) => (
        <DocumentPreview
          key={previewFile.id}
          registryKey={`library-preview:${previewFile.id}`}
          path={previewFile.file_name}
          signedUrl={previewFile.url ? getFullUrl(previewFile.url) : undefined}
          fileSize={previewFile.file_size}
          mimeType={previewFile.mime_type ?? undefined}
          onClose={() =>
            setPreviewFiles((current) =>
              current.filter((file) => file.id !== previewFile.id),
            )
          }
          mobileFillViewport
        />
      ))}

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
