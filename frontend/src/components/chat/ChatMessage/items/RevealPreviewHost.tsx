import { useEffect, useRef, useState } from "react";
import { Code2, Download, Maximize, Minimize } from "lucide-react";
import { useTranslation } from "react-i18next";
import DocumentPreview from "../../../documents/DocumentPreview";
import ProjectPreview from "../../../documents/previews/ProjectPreview";
import { LoadingSpinner } from "../../../common";
import { ToolResultPanel } from "./ToolResultPanel";
import { exportProjectZip } from "../../../../utils/exportProjectZip";
import {
  exitProjectPreviewFullscreen,
  isProjectPreviewFullscreen,
  requestProjectPreviewFullscreen,
  resolveProjectPreviewMode,
} from "./projectPreviewFullscreen";
import type {
  ParsedProjectRevealData,
  RevealPreviewRequest,
} from "./revealPreviewData";
import {
  getCachedProjectRevealFiles,
  loadProjectRevealFilesCached,
} from "./revealPreviewData";

function ProjectRevealPreviewPanel({
  project,
  openInFullscreen = false,
  onClose,
}: {
  project: ParsedProjectRevealData;
  openInFullscreen?: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [viewMode, setViewMode] = useState<"center" | "sidebar">("sidebar");
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 640);
  const [isBrowserFullscreen, setIsBrowserFullscreen] = useState(false);
  const panelElementRef = useRef<HTMLDivElement | null>(null);
  const cached =
    project.version === 2
      ? getCachedProjectRevealFiles(project.path || project.name)
      : null;
  const [loadedFiles, setLoadedFiles] = useState<Record<string, string> | null>(
    project.version === 1 ? project.files : cached?.files || null,
  );
  const [binaryFiles, setBinaryFiles] = useState<Record<string, string>>(
    cached?.binaryFiles || {},
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
  }, [project]);

  useEffect(() => {
    const syncFullscreenState = () => {
      setIsBrowserFullscreen(
        isProjectPreviewFullscreen({
          element: panelElementRef.current,
        }),
      );
    };

    syncFullscreenState();
    document.addEventListener("fullscreenchange", syncFullscreenState);
    return () =>
      document.removeEventListener("fullscreenchange", syncFullscreenState);
  }, []);

  useEffect(() => {
    if (project.version !== 2) return;

    let cancelled = false;
    const cacheKey = project.path || project.name;
    const nextCached = getCachedProjectRevealFiles(cacheKey);
    setLoadedFiles(nextCached?.files || null);
    setBinaryFiles(nextCached?.binaryFiles || {});
    setLoadingError(false);

    if (!cacheKey) {
      setLoadingError(true);
      return;
    }

    void loadProjectRevealFilesCached({
      previewKey: cacheKey,
      project,
    })
      .then(({ files, binaryFiles: nextBinaryFiles, failed }) => {
        if (cancelled) return;
        setBinaryFiles(nextBinaryFiles);
        setLoadedFiles(files);
        if (failed.length > 0) {
          console.warn(
            `[reveal_project] ${failed.length} files failed to load:`,
            failed,
          );
        }
        if (
          Object.keys(files).length === 0 &&
          Object.keys(project.files).length
        ) {
          setLoadingError(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLoadingError(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [project]);

  const enterBrowserFullscreen = async () => {
    const fullscreenEntered = await requestProjectPreviewFullscreen({
      element: panelElementRef.current,
    });

    if (!fullscreenEntered && !isMobile) {
      setViewMode((currentMode) =>
        resolveProjectPreviewMode(currentMode, fullscreenEntered),
      );
    }

    return fullscreenEntered;
  };

  const exitBrowserFullscreen = async () => {
    await exitProjectPreviewFullscreen();
  };

  useEffect(() => {
    if (!openInFullscreen) return;
    void enterBrowserFullscreen();
  }, [openInFullscreen, project]);

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
      headerActions={
        <>
          <button
            onClick={() => {
              if (isBrowserFullscreen) {
                void exitBrowserFullscreen();
                return;
              }
              void enterBrowserFullscreen();
            }}
            className="hidden sm:flex items-center justify-center w-8 h-8 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-all duration-200 active:scale-95"
            title={
              isBrowserFullscreen
                ? t("documents.exitFullscreen")
                : t("documents.fullscreen")
            }
          >
            {isBrowserFullscreen ? (
              <Minimize
                size={15}
                className="text-stone-400 dark:text-stone-500"
              />
            ) : (
              <Maximize
                size={15}
                className="text-stone-400 dark:text-stone-500"
              />
            )}
          </button>
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
        <div className="h-[300px] sm:h-[600px] bg-stone-900 flex items-center justify-center">
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
          isFullscreen={viewMode !== "sidebar" || isBrowserFullscreen}
          showHeader={false}
          onToggleSidebar={
            viewMode === "center" ? () => setViewMode("sidebar") : undefined
          }
        />
      )}
    </ToolResultPanel>
  );
}

export function RevealPreviewHost({
  preview,
  onClose,
}: {
  preview: RevealPreviewRequest | null;
  onClose: () => void;
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
      />
    );
  }

  return (
    <ProjectRevealPreviewPanel
      project={preview.project}
      openInFullscreen={preview.openInFullscreen}
      onClose={onClose}
    />
  );
}
