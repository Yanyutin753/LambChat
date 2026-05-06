import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Code2, FolderTree } from "lucide-react";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../../common";
import { LazyDocumentPreview } from "../../../documents/LazyDocumentPreview";
import { LazyProjectPreview } from "../../../documents/previews/LazyProjectPreview";
import { ToolResultPanel } from "./ToolResultPanel";
import { isImageFile } from "../../../documents/utils";
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
import { createActiveRevealPreviewState } from "./revealPreviewState";
import { setActiveRevealPreviewState } from "./activeRevealPreviewStore";
import { FileTreeView } from "./FileTreeView";
import type { TreeNode } from "./FileTreeView";

function ProjectRevealPreviewPanel({
  project,
  openInFullscreen = false,
  onClose,
  onUserInteraction,
  registryKey,
}: {
  project: ParsedProjectRevealData;
  openInFullscreen?: boolean;
  onClose: () => void;
  onUserInteraction?: () => void;
  registryKey?: string;
}) {
  const { t } = useTranslation();
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 640);
  const [viewMode, setViewMode] = useState<"center" | "sidebar">("sidebar");
  const [isBrowserFullscreen, setIsBrowserFullscreen] = useState(false);
  const isFolder = project.mode === "folder";
  const [showExplorer, setShowExplorer] = useState(isFolder);
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

  const handleFileClickInTree = useCallback(
    (node: TreeNode) => {
      if (!loadedFiles) return;
      const ext = node.name.split(".").pop()?.toLowerCase() || "";
      const filePreview: RevealPreviewRequest = {
        kind: "file",
        previewKey: `project-file:${node.path}`,
        filePath: node.name,
        ...(node.isBinary
          ? { signedUrl: node.url }
          : { content: loadedFiles[node.path] }),
        ...(isImageFile(ext) && node.isBinary && node.url
          ? { imageUrl: node.url }
          : {}),
        fileSize: node.size,
      };
      setActiveRevealPreviewState(
        createActiveRevealPreviewState(filePreview, "manual"),
      );
    },
    [loadedFiles],
  );

  return (
    <ToolResultPanel
      open={true}
      onClose={onClose}
      registryKey={registryKey}
      title={project.name || t("project.untitled")}
      icon={<Code2 size={16} />}
      status="success"
      subtitle={`${
        project.template !== "static" ? `${project.template} · ` : ""
      }${t("project.fileCount", {
        count: project.fileCount,
      })}`}
      viewMode={isMobile ? "center" : viewMode}
      onViewModeChange={(mode) => setViewMode(mode)}
      isFullscreen={isBrowserFullscreen}
      mobileFillViewport
      onFullscreenChange={(fs) => {
        if (fs) {
          void enterBrowserFullscreen();
        } else {
          if (document.fullscreenElement) {
            document.exitFullscreen();
          }
        }
      }}
      panelElementRef={panelElementRef}
      onUserInteraction={onUserInteraction}
      headerActions={
        !isFolder ? (
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => setShowExplorer(!showExplorer)}
              className={clsx(
                "flex items-center justify-center w-8 h-8 rounded-xl transition-all duration-200 active:scale-95",
                showExplorer
                  ? "bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400"
                  : "hover:bg-stone-100 dark:hover:bg-stone-800 text-stone-400 dark:text-stone-500",
              )}
              title={t("project.toggleExplorer", "切换文件浏览器")}
            >
              <FolderTree size={18} />
            </button>
          </div>
        ) : undefined
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
      ) : showExplorer || isFolder ? (
        <FileTreeView
          files={loadedFiles}
          binaryFiles={binaryFiles}
          projectName={project.name}
          onFileClick={handleFileClickInTree}
        />
      ) : (
        <LazyProjectPreview
          name={project.name}
          template={project.template}
          mode={project.mode}
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
      <LazyDocumentPreview
        key={preview.previewKey}
        path={preview.filePath}
        content={preview.content}
        s3Key={preview.s3Key}
        signedUrl={preview.signedUrl}
        imageUrl={preview.imageUrl}
        fileSize={preview.fileSize}
        onClose={onClose}
        onUserInteraction={onUserInteraction}
        registryKey={`reveal-preview:${preview.previewKey}`}
      />
    );
  }

  return (
    <ProjectRevealPreviewPanel
      key={preview.previewKey}
      project={preview.project}
      openInFullscreen={preview.openInFullscreen}
      onClose={onClose}
      onUserInteraction={onUserInteraction}
      registryKey={`reveal-preview:${preview.previewKey}`}
    />
  );
}
