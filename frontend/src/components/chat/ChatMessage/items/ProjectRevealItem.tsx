import { useEffect, useState } from "react";
import { Code2, FolderTree, Download, Maximize } from "lucide-react";
import { PreviewHeader } from "../../../common/FileIcon";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../../common";
import ProjectPreview from "../../../documents/previews/ProjectPreview";
import { exportProjectZip } from "../../../../utils/exportProjectZip";
import {
  getProjectRevealAutoOpenKey,
  markProjectRevealPreviewAutoOpened,
  shouldAutoOpenProjectRevealPreview,
} from "./projectRevealAutoOpen";
import {
  getCachedProjectRevealFiles,
  loadProjectRevealFilesCached,
  parseProjectRevealSummary,
  type RevealPreviewRequest,
} from "./revealPreviewData";

export function ProjectRevealItem({
  args,
  result,
  success,
  isPending,
  cancelled,
  allowAutoPreview,
  activePreview,
  onOpenPreview,
}: {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
  allowAutoPreview?: boolean;
  activePreview?: RevealPreviewRequest | null;
  onOpenPreview?: (preview: RevealPreviewRequest) => void;
}) {
  const { t } = useTranslation();
  const { projectName, template, error, fileCount, projectPath, parsed } =
    parseProjectRevealSummary({
      args,
      result,
      parseErrorMessage: t("chat.message.toolParseError"),
    });

  const projectAutoOpenKey = getProjectRevealAutoOpenKey({
    projectPath,
    projectName,
  });
  const isPreviewOpen =
    activePreview?.kind === "project" &&
    activePreview.previewKey === projectAutoOpenKey;
  const inlineFiles = parsed?.version === 1 ? parsed.files : null;
  const cachedProjectFiles =
    parsed?.version === 2
      ? getCachedProjectRevealFiles(projectAutoOpenKey)
      : null;
  const [loadedFiles, setLoadedFiles] = useState<Record<string, string> | null>(
    cachedProjectFiles?.files || inlineFiles,
  );
  const [binaryFiles, setBinaryFiles] = useState<Record<string, string>>(
    cachedProjectFiles?.binaryFiles || {},
  );
  const [loadingError, setLoadingError] = useState(false);

  const openPreview = (openInFullscreen = false) => {
    if (!parsed || !projectAutoOpenKey) return;
    onOpenPreview?.({
      kind: "project",
      previewKey: projectAutoOpenKey,
      project: parsed,
      openInFullscreen,
    });
  };

  useEffect(() => {
    const decision = shouldAutoOpenProjectRevealPreview({
      success,
      showFullPreview: isPreviewOpen,
      isDesktop: window.innerWidth >= 640,
      allowAutoPreview,
      previewKey: projectAutoOpenKey,
    });
    console.log("[ProjectRevealItem] auto-preview check", {
      projectName,
      projectPath,
      projectAutoOpenKey,
      success,
      showFullPreview: isPreviewOpen,
      allowAutoPreview,
      isDesktop: window.innerWidth >= 640,
      decision,
    });
    if (!decision || !parsed || !projectAutoOpenKey) {
      return;
    }

    markProjectRevealPreviewAutoOpened(projectAutoOpenKey);
    console.log("[ProjectRevealItem] auto-opening preview", {
      projectName,
      projectPath,
      projectAutoOpenKey,
    });
    onOpenPreview?.({
      kind: "project",
      previewKey: projectAutoOpenKey,
      project: parsed,
    });
  }, [
    success,
    isPreviewOpen,
    allowAutoPreview,
    projectAutoOpenKey,
    projectName,
    projectPath,
    parsed,
    onOpenPreview,
  ]);

  useEffect(() => {
    if (!projectName && !projectPath) return;
    console.log("[ProjectRevealItem] preview visibility changed", {
      projectName,
      projectPath,
      projectAutoOpenKey,
      showFullPreview: isPreviewOpen,
      viewMode: "sidebar",
    });
  }, [projectName, projectPath, projectAutoOpenKey, isPreviewOpen]);

  useEffect(() => {
    if (!parsed || parsed.version !== 2 || !projectAutoOpenKey || !success) {
      setLoadedFiles(inlineFiles);
      setBinaryFiles({});
      setLoadingError(false);
      return;
    }

    const cached = getCachedProjectRevealFiles(projectAutoOpenKey);
    setLoadedFiles(cached?.files || null);
    setBinaryFiles(cached?.binaryFiles || {});
    setLoadingError(false);

    let cancelled = false;
    void loadProjectRevealFilesCached({
      previewKey: projectAutoOpenKey,
      project: parsed,
    })
      .then(({ files, binaryFiles: nextBinaryFiles }) => {
        if (cancelled) return;
        setLoadedFiles(files);
        setBinaryFiles(nextBinaryFiles);
      })
      .catch(() => {
        if (!cancelled) {
          setLoadingError(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [parsed, projectAutoOpenKey, success, inlineFiles]);

  if (isPending) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-900">
        <div className="p-2.5 rounded-lg bg-stone-100 dark:bg-stone-800">
          <LoadingSpinner
            size="sm"
            className="text-stone-600 dark:text-stone-400"
          />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-stone-700 dark:text-stone-300 truncate">
            {projectName || t("project.loading")}
          </div>
          <div className="text-xs text-stone-500 dark:text-stone-400 truncate mt-0.5">
            {(args.project_path as string) || ""}
          </div>
        </div>
        <div className="text-xs text-amber-600 dark:text-amber-400">
          {t("chat.message.running")}
        </div>
      </div>
    );
  }

  if (cancelled && !result) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20">
        <div className="p-2.5 rounded-lg bg-amber-100 dark:bg-amber-900/30">
          <Code2 size={20} className="text-amber-500" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-stone-700 dark:text-stone-300 truncate">
            {projectName || t("project.loading")}
          </div>
          <div className="text-xs text-stone-500 dark:text-stone-400 truncate mt-0.5">
            {(args.project_path as string) || ""}
          </div>
        </div>
        <div className="text-xs text-amber-600 dark:text-amber-400">
          {t("chat.message.cancelled")}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20">
        <div className="p-2.5 rounded-lg bg-red-100 dark:bg-red-900/30">
          <Code2 size={20} className="text-red-500" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-red-700 dark:text-red-300 truncate">
            {projectName || t("project.error")}
          </div>
          <div className="text-xs text-red-500 dark:text-red-400 truncate mt-0.5">
            {error}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="my-2 sm:my-3 min-w-0">
      <div
        className="border border-stone-200 dark:border-stone-700 rounded-xl overflow-hidden bg-white dark:bg-stone-900 cursor-pointer hover:border-stone-300 dark:hover:border-stone-600 transition-colors"
        onClick={() => openPreview()}
      >
        <PreviewHeader
          variant="card"
          icon={Code2}
          title={projectName || t("project.untitled")}
          subtitle={`${t("project.fileCount", { count: fileCount })}${
            template !== "static" ? ` · ${template}` : ""
          }`}
          actions={
            <>
              {loadedFiles && (
                <button
                  onClick={(event) => {
                    event.stopPropagation();
                    exportProjectZip(loadedFiles, projectName, binaryFiles);
                  }}
                  className="flex items-center gap-1 px-1.5 sm:px-2 py-1 rounded-md text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-800 text-xs font-medium transition-colors"
                >
                  <Download size={14} />
                  <span className="hidden sm:inline">
                    {t("project.exportZip")}
                  </span>
                </button>
              )}
              <button
                onClick={(event) => {
                  event.stopPropagation();
                  openPreview(true);
                }}
                className="flex items-center gap-1 px-1.5 sm:px-2 py-1 rounded-md text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-800 text-xs font-medium transition-colors"
              >
                <Maximize size={14} />
                <span className="hidden sm:inline">
                  {t("project.fullscreen", "全屏")}
                </span>
              </button>
            </>
          }
        />

        {loadedFiles ? (
          <div className="h-[300px] sm:h-[600px] bg-stone-100 dark:bg-stone-900">
            <ProjectPreview
              name={projectName}
              template={template}
              files={loadedFiles}
              entry={parsed?.entry}
              showHeader={false}
              showTabs={true}
            />
          </div>
        ) : loadingError ? (
          <div className="h-[220px] sm:h-[320px] bg-stone-50 dark:bg-stone-950 border-t border-stone-200 dark:border-stone-800 flex items-center justify-center px-6 text-center">
            <div className="max-w-sm space-y-3">
              <div className="mx-auto size-12 rounded-2xl bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                <FolderTree
                  size={22}
                  className="text-amber-600 dark:text-amber-400"
                />
              </div>
              <div className="text-sm font-medium text-amber-700 dark:text-amber-300">
                {t("project.loadFilesFailed")}
              </div>
            </div>
          </div>
        ) : (
          <div className="h-[220px] sm:h-[320px] bg-stone-50 dark:bg-stone-950 border-t border-stone-200 dark:border-stone-800 flex items-center justify-center px-6 text-center">
            <div className="max-w-sm space-y-3">
              <div className="mx-auto size-12 rounded-2xl bg-stone-100 dark:bg-stone-800 flex items-center justify-center">
                <FolderTree
                  size={22}
                  className="text-stone-500 dark:text-stone-400"
                />
              </div>
              <div className="text-sm font-medium text-stone-700 dark:text-stone-200">
                {t("project.loadingFiles")}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
