import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Code2, FolderTree } from "lucide-react";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { LoadingSpinner, ImageViewer } from "../../../common";
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
import type { PluginRuntimeContributionStates } from "../../../../extensions/coreContributions";
import {
  getCachedProjectRevealFiles,
  loadProjectRevealFilesCached,
  shouldShowProjectRevealLoadingError,
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

interface ImageNodeInfo {
  path: string;
  name: string;
  url: string;
}

function collectImageNodes(
  files: Record<string, string>,
  binaryFiles: Record<string, string>,
): ImageNodeInfo[] {
  const images: ImageNodeInfo[] = [];
  const seen = new Set<string>();
  const allPaths = [...Object.keys(binaryFiles), ...Object.keys(files)].sort();
  for (const filePath of allPaths) {
    if (seen.has(filePath)) continue;
    seen.add(filePath);
    const name = filePath.replace(/^\/?/, "").split("/").pop() || "";
    const ext = name.split(".").pop()?.toLowerCase() || "";
    if (!isImageFile(ext)) continue;
    const url = binaryFiles[filePath];
    if (url) {
      images.push({ path: filePath, name, url });
    } else if (files[filePath]) {
      images.push({
        path: filePath,
        name,
        url: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
          files[filePath],
        )}`,
      });
    }
  }
  return images;
}

function ProjectRevealPreviewPanel({
  project,
  openInFullscreen = false,
  onClose,
  onUserInteraction,
  registryKey,
  footer,
}: {
  project: ParsedProjectRevealData;
  openInFullscreen?: boolean;
  onClose: () => void;
  onUserInteraction?: () => void;
  registryKey?: string;
  footer?: React.ReactNode;
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
  const [activeImagePath, setActiveImagePath] = useState<string | null>(null);

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
        const nextLoadingError = shouldShowProjectRevealLoadingError({
          files,
          binaryFiles: nextBinaryFiles,
          manifestFiles: project.files,
        });
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

  const imageNodes = useMemo(
    () => (loadedFiles ? collectImageNodes(loadedFiles, binaryFiles) : []),
    [loadedFiles, binaryFiles],
  );
  const activeImageIndex = activeImagePath
    ? imageNodes.findIndex((img) => img.path === activeImagePath)
    : -1;
  const activeImage =
    activeImageIndex >= 0 ? imageNodes[activeImageIndex] : null;
  const previousImage =
    activeImageIndex > 0 ? imageNodes[activeImageIndex - 1] : null;
  const nextImage =
    activeImageIndex >= 0 && activeImageIndex < imageNodes.length - 1
      ? imageNodes[activeImageIndex + 1]
      : null;
  const imagePositionLabel =
    activeImageIndex >= 0 && imageNodes.length > 1
      ? `${activeImageIndex + 1} / ${imageNodes.length}`
      : undefined;

  const handleFileClickInTree = useCallback(
    (node: TreeNode) => {
      if (!loadedFiles) return;
      const ext = node.name.split(".").pop()?.toLowerCase() || "";
      if (isImageFile(ext)) {
        const url = node.isBinary ? node.url : loadedFiles[node.path];
        if (url) {
          setActiveImagePath(node.path);
          return;
        }
      }
      const filePreview: RevealPreviewRequest = {
        kind: "file",
        previewKey: `project-file:${node.path}`,
        filePath: node.name,
        ...(node.isBinary
          ? { signedUrl: node.url }
          : { content: loadedFiles[node.path] }),
        fileSize: node.size,
      };
      setActiveRevealPreviewState(
        createActiveRevealPreviewState(filePreview, "manual"),
      );
    },
    [loadedFiles],
  );

  return (
    <>
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
        footer={footer}
        headerActions={
          !isFolder ? (
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={() => setShowExplorer(!showExplorer)}
                className={clsx(
                  "flex items-center justify-center w-8 h-8 rounded-xl transition-all duration-200 active:scale-95",
                  showExplorer
                    ? "bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400"
                    : "hover:bg-theme-bg-subtle text-theme-text-tertiary",
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
          <div className="h-full bg-theme-bg-elevated flex items-center justify-center">
            <div className="text-theme-text-tertiary text-sm flex items-center gap-2">
              <LoadingSpinner size="sm" className="text-theme-text-tertiary" />
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
      {activeImage && (
        <ImageViewer
          src={activeImage.url}
          alt={activeImage.name}
          isOpen={!!activeImage}
          onClose={() => setActiveImagePath(null)}
          onPrevious={() =>
            previousImage && setActiveImagePath(previousImage.path)
          }
          onNext={() => nextImage && setActiveImagePath(nextImage.path)}
          hasPrevious={!!previousImage}
          hasNext={!!nextImage}
          positionLabel={imagePositionLabel}
        />
      )}
    </>
  );
}

export function RevealPreviewHost({
  preview,
  onClose,
  onUserInteraction,
  runtimePlugins,
}: {
  preview: RevealPreviewRequest | null;
  onClose: () => void;
  onUserInteraction?: () => void;
  runtimePlugins?: PluginRuntimeContributionStates;
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
        mobileFillViewport
        footer={preview.footer}
        runtimePlugins={runtimePlugins}
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
      footer={preview.footer}
    />
  );
}
