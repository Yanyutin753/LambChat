import { InteractiveIcon } from "../../../common/InteractiveIcon";
import { useEffect, useMemo, useState } from "react";
import { Code2, FolderTree, Download, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../../common";
import { exportProjectZip } from "../../../../utils/exportProjectZip";
import {
  getProjectRevealAutoOpenKey,
  markProjectRevealPreviewAutoOpened,
  shouldAutoOpenProjectRevealPreview,
} from "./projectRevealAutoOpen";
import {
  getCachedProjectRevealFiles,
  isManifestProject,
  loadProjectRevealFilesCached,
  parseProjectRevealSummary,
  type RevealPreviewRequest,
} from "./revealPreviewData";
import {
  areStringRecordMapsEqual,
  normalizeProjectRevealBinaryFiles,
  shouldLoadProjectRevealFiles,
  shouldReplaceProjectRevealFiles,
} from "./projectRevealState";
import type { RevealPreviewOpenSource } from "./revealPreviewState";
import { openRevealPreview } from "./revealPreviewActions";
import { RevealStatusLabel, RevealStatusText } from "./RevealStatusText";

export function ProjectRevealItem({
  args,
  result,
  success,
  isPending,
  cancelled,
  allowAutoPreview,
  activePreview,
  onOpenPreview,
  startedAt,
  completedAt,
}: {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
  allowAutoPreview?: boolean;
  activePreview?: RevealPreviewRequest | null;
  onOpenPreview?: (
    preview: RevealPreviewRequest,
    source?: RevealPreviewOpenSource,
  ) => boolean;
  startedAt?: string;
  completedAt?: string;
}) {
  const { t } = useTranslation();
  const durationFooter = useMemo(() => {
    if (!startedAt || !completedAt) return undefined;
    const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
    if (ms < 0) return undefined;
    const seconds = Math.round(ms / 1000);
    const text =
      seconds < 60
        ? t("chat.message.toolTimeSeconds", { count: seconds })
        : t("chat.message.toolTimeMinutes", {
            minutes: Math.floor(seconds / 60),
            seconds: seconds % 60,
          });
    return (
      <span className="inline-flex items-center gap-1 text-12 text-[var(--theme-text-secondary)] tabular-nums px-2">
        <Clock size={11} className="shrink-0" />
        {text}
      </span>
    );
  }, [startedAt, completedAt, t]);
  const { projectName, mode, template, error, fileCount, projectPath, parsed } =
    useMemo(
      () =>
        parseProjectRevealSummary({
          args,
          result,
          parseErrorMessage: t("chat.message.toolParseError"),
        }),
      [args, result, t],
    );

  const projectAutoOpenKey = useMemo(
    () =>
      getProjectRevealAutoOpenKey({
        projectPath,
        projectName,
      }),
    [projectName, projectPath],
  );
  const isPreviewOpen =
    activePreview?.kind === "project" &&
    activePreview.previewKey === projectAutoOpenKey;
  const inlineFiles = parsed?.version === 1 ? parsed.files : null;
  const cachedProjectFiles = useMemo(
    () =>
      isManifestProject(parsed)
        ? getCachedProjectRevealFiles(projectAutoOpenKey)
        : null,
    [parsed, projectAutoOpenKey],
  );
  const [loadedFiles, setLoadedFiles] = useState<Record<string, string> | null>(
    cachedProjectFiles?.files || inlineFiles,
  );
  const [binaryFiles, setBinaryFiles] = useState<Record<string, string>>(
    normalizeProjectRevealBinaryFiles(cachedProjectFiles?.binaryFiles),
  );
  const shouldLoadFiles = shouldLoadProjectRevealFiles({
    isVersionedProject: isManifestProject(parsed),
    success,
    isPreviewOpen,
    allowAutoPreview,
  });
  const previewRequest = useMemo(() => {
    if (!parsed || !projectAutoOpenKey) return null;

    return {
      kind: "project" as const,
      previewKey: projectAutoOpenKey,
      project: parsed,
      footer: durationFooter,
    };
  }, [parsed, projectAutoOpenKey, durationFooter]);

  const openPreview = (
    openInFullscreen = false,
    source: RevealPreviewOpenSource = "manual",
  ) => {
    if (!previewRequest) return;
    openRevealPreview(
      {
        ...previewRequest,
        openInFullscreen,
      },
      source,
      onOpenPreview,
    );
  };

  useEffect(() => {
    const decision = shouldAutoOpenProjectRevealPreview({
      success,
      showFullPreview: isPreviewOpen,
      isDesktop: window.innerWidth >= 640,
      allowAutoPreview,
      previewKey: projectAutoOpenKey,
    });
    if (!decision || !previewRequest || !projectAutoOpenKey) {
      return;
    }

    const opened = openRevealPreview(previewRequest, "auto", onOpenPreview);

    if (opened) {
      markProjectRevealPreviewAutoOpened(projectAutoOpenKey);
    }
  }, [
    success,
    isPreviewOpen,
    allowAutoPreview,
    projectAutoOpenKey,
    previewRequest,
    onOpenPreview,
  ]);

  useEffect(() => {
    if (
      !parsed ||
      !isManifestProject(parsed) ||
      !projectAutoOpenKey ||
      !shouldLoadFiles
    ) {
      const cached = isManifestProject(parsed)
        ? getCachedProjectRevealFiles(projectAutoOpenKey)
        : null;
      const nextLoadedFiles = cached?.files || inlineFiles;
      const nextBinaryFiles = normalizeProjectRevealBinaryFiles(
        cached?.binaryFiles,
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
      return;
    }

    const cached = getCachedProjectRevealFiles(projectAutoOpenKey);
    const nextLoadedFiles = cached?.files || null;
    const nextBinaryFiles = normalizeProjectRevealBinaryFiles(
      cached?.binaryFiles,
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

    let cancelled = false;
    void loadProjectRevealFilesCached({
      previewKey: projectAutoOpenKey,
      project: parsed,
    })
      .then(({ files, binaryFiles: loadedBinaryFiles }) => {
        if (cancelled) return;
        const nextBinaryFiles =
          normalizeProjectRevealBinaryFiles(loadedBinaryFiles);
        setLoadedFiles((current) =>
          shouldReplaceProjectRevealFiles(current, files) ? files : current,
        );
        setBinaryFiles((current) =>
          areStringRecordMapsEqual(current, nextBinaryFiles)
            ? current
            : nextBinaryFiles,
        );
      })
      .catch(() => {
        if (!cancelled) {
          // File loading failed silently; preview panel will handle retry
        }
      });

    return () => {
      cancelled = true;
    };
  }, [parsed, projectAutoOpenKey, shouldLoadFiles, inlineFiles]);

  if (isPending) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-theme-border bg-theme-bg-card">
        <div className="p-2.5 rounded-lg bg-theme-bg-subtle">
          <LoadingSpinner size="sm" className="text-theme-text-secondary" />
        </div>
        <RevealStatusText
          title={projectName || t("project.loading")}
          subtitle={(args.project_path as string) || ""}
        />
        <RevealStatusLabel>{t("chat.message.running")}</RevealStatusLabel>
      </div>
    );
  }

  if (cancelled && !result) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20">
        <div className="p-2.5 rounded-lg bg-amber-100 dark:bg-amber-900/30">
          <Code2 size={20} className="text-amber-500" />
        </div>
        <RevealStatusText
          title={projectName || t("project.loading")}
          subtitle={(args.project_path as string) || ""}
        />
        <RevealStatusLabel>{t("chat.message.cancelled")}</RevealStatusLabel>
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
          <div className="text-14 font-medium text-red-700 dark:text-red-300 truncate">
            {projectName || t("project.error")}
          </div>
          <div className="text-12 text-red-500 dark:text-red-400 truncate mt-0.5">
            {error}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="my-2 sm:my-3 min-w-0">
      <div
        className="flex items-center gap-3 px-3 sm:px-4 py-2.5 sm:py-3 rounded-2xl ring-1 ring-theme-border bg-theme-bg-card cursor-pointer hover:ring-theme-border-hover transition-all duration-200 shadow-sm hover:shadow-md"
        onClick={() => openPreview()}
      >
        <div className="flex items-center justify-center size-10 rounded-xl shrink-0 bg-[var(--theme-primary-light)]">
          {mode === "folder" ? (
            <FolderTree size={20} className="text-[var(--theme-primary)]" />
          ) : (
            <Code2 size={20} className="text-[var(--theme-primary)]" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-14 font-medium text-theme-text truncate">
            {projectName || t("project.untitled")}
          </div>
          <div className="text-12 text-theme-text-tertiary mt-0.5 truncate">
            {t("project.fileCount", { count: fileCount })}
            {mode === "project" && template !== "static"
              ? ` · ${template}`
              : ""}
          </div>
        </div>
        <div className="shrink-0 flex items-center gap-1 relative z-10">
          {loadedFiles && (
            <button
              onClick={(event) => {
                event.stopPropagation();
                exportProjectZip(loadedFiles, projectName, binaryFiles);
              }}
              className="flex items-center justify-center size-8 rounded-lg text-theme-text-tertiary hover:text-theme-text-secondary hover:bg-theme-bg-hover transition-colors"
              title={t("project.exportZip")}
            >
              <InteractiveIcon>
                <Download size={16} />
              </InteractiveIcon>
            </button>
          )}
          <button
            onClick={(event) => {
              event.stopPropagation();
              openPreview();
            }}
            className="px-3 py-1.5 rounded-lg text-12 font-medium bg-theme-bg-subtle text-theme-text-secondary hover:bg-theme-bg-hover transition-colors"
          >
            {t("project.preview", "预览")}
          </button>
        </div>
      </div>
    </div>
  );
}
