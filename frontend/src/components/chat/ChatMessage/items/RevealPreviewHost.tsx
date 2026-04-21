import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Code2, Download, Maximize } from "lucide-react";
import { useTranslation } from "react-i18next";
import DocumentPreview from "../../../documents/DocumentPreview";
import ProjectPreview from "../../../documents/previews/ProjectPreview";
import { LoadingSpinner } from "../../../common";
import { ToolResultPanel } from "./ToolResultPanel";
import { exportProjectZip } from "../../../../utils/exportProjectZip";
import {
  isProjectPreviewFullscreen,
  requestProjectPreviewFullscreen,
} from "./projectPreviewFullscreen";
import type {
  ParsedProjectRevealData,
  RevealPreviewRequest,
} from "./revealPreviewData";
import {
  getCachedProjectRevealFiles,
  loadProjectRevealFilesCached,
} from "./revealPreviewData";
import {
  EMPTY_BINARY_FILES,
  areStringRecordMapsEqual,
  normalizeProjectRevealBinaryFiles,
  shouldReplaceProjectRevealFiles,
} from "./projectRevealState";

function ProjectRevealPreviewPanel({
  project,
  openInFullscreen = false,
  onClose,
  onUserInteraction,
}: {
  project: ParsedProjectRevealData;
  openInFullscreen?: boolean;
  onClose: () => void;
  onUserInteraction?: () => void;
}) {
  const { t } = useTranslation();
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 640);
  const [viewMode, setViewMode] = useState<"center" | "sidebar">("sidebar");
  const [isBrowserFullscreen, setIsBrowserFullscreen] = useState(false);
  const panelElementRef = useRef<HTMLDivElement | null>(null);
  const cacheKey = useMemo(
    () => project.path || project.name,
    [project.name, project.path],
  );
  const cached = useMemo(
    () =>
      project.version === 2 ? getCachedProjectRevealFiles(cacheKey) : null,
    [cacheKey, project.version],
  );
  const [loadedFiles, setLoadedFiles] = useState<Record<string, string> | null>(
    project.version === 1 ? project.files : cached?.files || null,
  );
  const [binaryFiles, setBinaryFiles] = useState<Record<string, string>>(
    normalizeProjectRevealBinaryFiles(cached?.binaryFiles),
  );
  const [loadingError, setLoadingError] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    setIsMobile(mq.matches);
    const handler = (event: MediaQueryListEvent) => setIsMobile(event.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  useEffect(() => {
    setViewMode("sidebar");
  }, [cacheKey]);

  useEffect(() => {
    const syncFullscreenState = () => {
      const fullscreen = isProjectPreviewFullscreen({
        element: panelElementRef.current,
      });
      setIsBrowserFullscreen(fullscreen);
      setViewMode(fullscreen ? "center" : "sidebar");
    };

    syncFullscreenState();
    document.addEventListener("fullscreenchange", syncFullscreenState);
    return () =>
      document.removeEventListener("fullscreenchange", syncFullscreenState);
  }, []);

  useEffect(() => {
    if (project.version !== 2) {
      setLoadedFiles((current) =>
        shouldReplaceProjectRevealFiles(current, project.files)
          ? project.files
          : current,
      );
      setBinaryFiles((current) =>
        areStringRecordMapsEqual(current, EMPTY_BINARY_FILES)
          ? current
          : EMPTY_BINARY_FILES,
      );
      setLoadingError((current) => (current ? false : current));
      return;
    }

    let cancelled = false;
    const nextCached = getCachedProjectRevealFiles(cacheKey);
    const nextLoadedFiles = nextCached?.files || null;
    const nextBinaryFiles = normalizeProjectRevealBinaryFiles(
      nextCached?.binaryFiles,
    );
    setLoadedFiles((current) =>
      shouldReplaceProjectRevealFiles(current, nextLoadedFiles)
        ? nextLoadedFiles
        : current,
    );
    setBinaryFiles((current) =>
      areStringRecordMapsEqual(current, nextBinaryFiles)
        ? current
        : nextBinaryFiles,
    );
    setLoadingError((current) => (current ? false : current));

    if (!cacheKey) {
      setLoadingError((current) => (current ? current : true));
      return;
    }

    void loadProjectRevealFilesCached({
      previewKey: cacheKey,
      project,
    })
      .then(({ files, binaryFiles: loadedBinaryFiles, failed }) => {
        if (cancelled) return;
        const nextBinaryFiles =
          normalizeProjectRevealBinaryFiles(loadedBinaryFiles);
        setBinaryFiles((current) =>
          areStringRecordMapsEqual(current, nextBinaryFiles)
            ? current
            : nextBinaryFiles,
        );
        setLoadedFiles((current) =>
          shouldReplaceProjectRevealFiles(current, files) ? files : current,
        );
        if (failed.length > 0) {
          console.warn(
            `[reveal_project] ${failed.length} files failed to load:`,
            failed,
          );
        }
        const nextLoadingError =
          Object.keys(files).length === 0 &&
          Object.keys(project.files).length > 0;
        setLoadingError((current) =>
          current === nextLoadingError ? current : nextLoadingError,
        );
      })
      .catch(() => {
        if (!cancelled) {
          setLoadingError((current) => (current ? current : true));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [cacheKey, project]);

  const enterBrowserFullscreen = useCallback(async () => {
    const fullscreenEntered = await requestProjectPreviewFullscreen({
      element: panelElementRef.current,
    });

    return fullscreenEntered;
  }, []);

  useEffect(() => {
    if (!openInFullscreen) return;
    void enterBrowserFullscreen();
  }, [openInFullscreen, cacheKey, enterBrowserFullscreen]);

  const filesForPreview = loadedFiles || {};

  return (
    <ToolResultPanel
      open={true}
      onClose={onClose}
      title={project.name || t("project.untitled")}
      icon={<Code2 size={16} />}
      status="success"
      subtitle={`${
        project.template !== "static" ? `${project.template} · ` : ""
      }${t("project.fileCount", {
        count: project.fileCount,
      })}`}
      viewMode={isMobile ? "center" : viewMode}
      panelElementRef={panelElementRef}
      onUserInteraction={onUserInteraction}
      headerActions={
        <>
          {!isBrowserFullscreen && (
            <button
              onClick={() => {
                onUserInteraction?.();
                void enterBrowserFullscreen();
              }}
              className="hidden sm:flex items-center justify-center w-8 h-8 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-all duration-200 active:scale-95"
              title={t("documents.fullscreen")}
            >
              <Maximize
                size={15}
                className="text-stone-400 dark:text-stone-500"
              />
            </button>
          )}
          <button
            onClick={() =>
              exportProjectZip(filesForPreview, project.name, binaryFiles)
            }
            className="flex items-center justify-center w-8 h-8 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-all duration-200 active:scale-95"
            title={t("project.exportZip")}
            disabled={!loadedFiles || loadingError}
          >
            <Download
              size={15}
              className="text-stone-400 dark:text-stone-500"
            />
          </button>
        </>
      }
    >
      {loadingError ? (
        <div className="p-6 text-sm text-amber-600 dark:text-amber-400">
          {t("project.loadFilesFailed")}
        </div>
      ) : !loadedFiles ? (
        <div className="h-full bg-stone-900 flex items-center justify-center">
          <div className="text-stone-400 text-sm flex items-center gap-2">
            <LoadingSpinner size="sm" className="text-stone-400" />
            {t("project.loadingFiles")}
          </div>
        </div>
      ) : (
        <ProjectPreview
          name={project.name}
          template={project.template}
          files={filesForPreview}
          entry={project.entry}
          isFullscreen={viewMode === "center" || isBrowserFullscreen}
          showHeader={false}
          onToggleSidebar={
            viewMode === "center" && !isBrowserFullscreen
              ? () => setViewMode("sidebar")
              : undefined
          }
        />
      )}
    </ToolResultPanel>
  );
}

export function RevealPreviewHost({
  preview,
  onClose,
  onUserInteraction,
}: {
  preview: RevealPreviewRequest | null;
  onClose: () => void;
  onUserInteraction?: () => void;
}) {
  if (!preview) {
    return null;
  }

  if (preview.kind === "file") {
    return (
      <DocumentPreview
        path={preview.filePath}
        s3Key={preview.s3Key}
        signedUrl={preview.signedUrl}
        fileSize={preview.fileSize}
        onClose={onClose}
        onUserInteraction={onUserInteraction}
      />
    );
  }

  return (
    <ProjectRevealPreviewPanel
      project={preview.project}
      openInFullscreen={preview.openInFullscreen}
      onClose={onClose}
      onUserInteraction={onUserInteraction}
    />
  );
}
