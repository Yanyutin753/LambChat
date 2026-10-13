import { LoadingSpinner } from "../../common/LoadingSpinner";
import { type ReactNode, useCallback, useId, useMemo, useState } from "react";
import {
  FolderTree,
  Code2,
  ChevronRight,
  ChevronDown,
  Download,
} from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import type { MessagePart } from "../../../types";
import { getFileTypeInfo, isImageFile } from "../../documents/utils";
import { ImageViewer } from "../../common";
import { CopyButton } from "../../common/CopyButton";
import { Button, ToolbarIconButton } from "../../common/ui";
import { Tooltip } from "../../common/Tooltip";
import { openPersistentToolPanel } from "./items/persistentToolPanelState";
import type { RevealPreviewOpenSource } from "./items/revealPreviewState";
import type { RevealPreviewRequest } from "./items/revealPreviewData";
import {
  buildRevealArtifactBinaryFiles,
  buildRevealArtifactTree,
  collectRevealArtifacts,
  getRevealArtifactStats,
  type RevealArtifact,
  type RevealArtifactTreeDir,
  type RevealArtifactTreeFile,
} from "./revealArtifacts";
import { ImageWithSkeleton } from "./ImageWithSkeleton";
import { exportProjectZip } from "../../../utils/exportProjectZip";

function FolderIcon({
  size = 36,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 1024 1024"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M54.9632 228.8128c-1.152-21.376 0.64-43.1872 10.0352-62.4128 13.696-28.032 32.2816-45.7728 59.776-57.9072 17.1008-7.552 36.0448-9.344 54.7328-9.344h196.5056a93.696 93.696 0 0 1 59.0592 21.248l38.4512 31.1552a76.8 76.8 0 0 0 48.384 17.152h316.1088c54.1952 0 98.0992 43.5968 98.0992 97.3824l17.792 538.4704c0 53.7856-24.5248 83.456-77.0048 111.3088H184.32c-45.6192-27.8528-70.144-55.6544-98.0992-97.3824L54.9632 228.8128z"
        fill="#FFE8A3"
      />
      <path
        d="M170.1632 310.9632a51.2 51.2 0 0 1 51.2-51.2h601.344a51.2 51.2 0 0 1 51.2 51.2v397.7216a128 128 0 0 1-128 128h-447.744a128 128 0 0 1-128-128V310.9632z"
        fill="#FFCF40"
      />
      <path
        d="M116.736 413.5424a107.9296 107.9296 0 0 1 30.9248-68.1984 92.9792 92.9792 0 0 1 65.536-27.5968H882.176c13.2352 0 26.368 2.944 38.5024 8.6272 12.1344 5.7088 23.0912 14.0288 32.1536 24.4736 9.0368 10.4448 16.0256 22.784 20.48 36.2496 4.48 13.4656 6.3232 27.776 5.4528 42.0608l-24.1152 397.9776a108.1856 108.1856 0 0 1-30.464 69.4784 93.056 93.056 0 0 1-66.176 28.2368h-675.84a90.7264 90.7264 0 0 1-38.912-8.8064c-12.288-5.8368-23.296-14.336-32.384-24.9856a106.5984 106.5984 0 0 1-20.3264-36.9152 112.4352 112.4352 0 0 1-4.864-42.6496l31.0016-397.952z"
        fill="#FFE8A3"
      />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Tree renderer                                                      */
/* ------------------------------------------------------------------ */

const FILE_ICON_SIZE = 24;

function formatSize(bytes?: number): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function downloadFile(name: string, url?: string) {
  if (!url) return;
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
}

function getDownloadFailureMessage(
  baseMessage: string,
  error: unknown,
): string {
  return error instanceof Error && error.message
    ? `${baseMessage}: ${error.message}`
    : baseMessage;
}

function getTreeDirSize(node: RevealArtifactTreeDir): number {
  return node.children.reduce((sum, child) => {
    if (child.kind === "file") {
      return sum + (child.artifact.fileSize || 0);
    }
    return sum + getTreeDirSize(child);
  }, 0);
}

function collectSubtreeFiles(
  node: RevealArtifactTreeDir,
): (RevealArtifact & { kind: "file" })[] {
  const out: (RevealArtifact & { kind: "file" })[] = [];
  for (const child of node.children) {
    if (child.kind === "file") {
      out.push(child.artifact);
    } else {
      out.push(...collectSubtreeFiles(child));
    }
  }
  return out;
}

function getFileIcon(name: string) {
  const info = getFileTypeInfo(name);
  const Icon = info.icon;
  return (
    <Icon size={FILE_ICON_SIZE} className={clsx("shrink-0", info.color)} />
  );
}

function TreeFileRow({
  node,
  onOpenPreview,
  onOpenImagePreview,
  inline = false,
}: {
  inline?: boolean;
  node: RevealArtifactTreeFile;
  onOpenPreview?: (
    preview: RevealPreviewRequest,
    source?: RevealPreviewOpenSource,
  ) => boolean;
  onOpenImagePreview?: (artifact: RevealArtifact & { kind: "file" }) => void;
}) {
  const { t } = useTranslation();
  const ext = node.artifact.name.split(".").pop()?.toLowerCase() || "";
  const imageSrc = isImageFile(ext) ? node.artifact.preview.signedUrl : null;
  const fileType = getFileTypeInfo(node.artifact.name);
  const FileIcon = fileType.icon;

  return (
    <div
      data-inline-attachment={inline || undefined}
      className={clsx(
        "group flex min-w-0 max-w-full items-center gap-1 w-full transition-colors motion-reduce:transition-none",
        inline
          ? "px-3 py-2 hover:bg-theme-text/[0.04]"
          : "rounded-xl px-3 py-2.5 hover:bg-theme-bg-subtle",
      )}
    >
      <Tooltip content={node.artifact.name}>
        <button
          type="button"
          aria-label={node.artifact.name}
          onClick={() => {
            if (imageSrc && onOpenImagePreview) {
              onOpenImagePreview(node.artifact);
              return;
            }
            onOpenPreview?.(node.artifact.preview, "manual");
          }}
          className="flex min-w-0 min-h-[44px] flex-1 items-center gap-3 text-left cursor-pointer rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)]"
        >
          {imageSrc ? (
            <span
              className={inline ? "flex h-8 w-8 shrink-0 items-center justify-center" : "contents"}
            >
              <ImageWithSkeleton
                src={imageSrc}
                alt={node.artifact.name}
                skipUrlResolve
                inline
                className={clsx(
                  inline ? "w-6 h-6" : "w-9 h-9",
                  "rounded-lg object-cover shrink-0 bg-stone-100 dark:bg-stone-800",
                )}
              />
            </span>
          ) : inline ? (
            <span className="flex h-8 w-8 shrink-0 items-center justify-center text-theme-text-secondary">
              <FileIcon size={24} strokeWidth={1.5} className={fileType.color} />
            </span>
          ) : (
            getFileIcon(node.artifact.name)
          )}
          <div className="flex-1 min-w-0 text-left">
            <div
              className={clsx(
                "text-14 text-theme-text-secondary",
                inline
                  ? "truncate leading-5"
                  : "line-clamp-2 break-all text-balance",
              )}
            >
              {node.artifact.name}
            </div>
            <div
              className={clsx(
                "text-theme-text-tertiary mt-0.5 truncate",
                inline ? "font-mono text-11 tracking-tight" : "text-12",
              )}
            >
              {inline
                ? [ext.toUpperCase(), formatSize(node.artifact.fileSize)]
                    .filter(Boolean)
                    .join(" · ")
                : node.artifact.fileSize
                  ? formatSize(node.artifact.fileSize)
                  : node.artifact.description || node.artifact.path}
            </div>
          </div>
        </button>
      </Tooltip>
      <div className="flex shrink-0 items-center gap-1 opacity-100 sm:[@media(hover:hover)_and_(pointer:fine)]:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
        <Tooltip content={t("documents.downloadFile")}>
          <ToolbarIconButton
            variant="muted"
            disabled={!node.artifact.preview.signedUrl}
            onClick={() => {
              downloadFile(node.artifact.name, node.artifact.preview.signedUrl);
            }}
            aria-label={`${t("documents.downloadFile")}: ${node.artifact.name}`}
            icon={<Download size={18} />}
          />
        </Tooltip>
        {!inline && (
          <CopyButton
            text={node.artifact.preview.signedUrl || node.artifact.path}
            size={18}
          />
        )}
      </div>
    </div>
  );
}

function TreeDirRow({
  node,
  depth,
  defaultExpanded,
  onOpenPreview,
  onOpenImagePreview,
}: {
  node: RevealArtifactTreeDir;
  depth: number;
  defaultExpanded?: boolean;
  onOpenPreview?: (
    preview: RevealPreviewRequest,
    source?: RevealPreviewOpenSource,
  ) => boolean;
  onOpenImagePreview?: (artifact: RevealArtifact & { kind: "file" }) => void;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(defaultExpanded ?? false);
  const [isDownloading, setIsDownloading] = useState(false);
  const dirSize = expanded ? getTreeDirSize(node) : 0;
  const { binaryFiles, skippedCount, skippedPaths } = useMemo(
    () => buildRevealArtifactBinaryFiles(collectSubtreeFiles(node)),
    [node],
  );
  const hasDownloadableFiles = Object.keys(binaryFiles).length > 0;
  const toggleExpanded = () => setExpanded(!expanded);
  const toggleLabel = `${t(expanded ? "common.collapse" : "common.expand")}: ${
    node.name
  }`;

  return (
    <div className="min-w-0 max-w-full">
      <div className="flex min-w-0 max-w-full w-full items-center gap-3 overflow-hidden px-3 py-2.5 rounded-xl hover:bg-stone-50 dark:hover:bg-stone-800/60 transition-colors group">
        <button
          type="button"
          aria-expanded={expanded}
          onClick={toggleExpanded}
          className="flex !min-w-0 min-h-[44px] flex-1 items-center gap-3 text-left rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)]"
        >
          <FolderIcon size={36} className="shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-14 font-medium text-stone-800 dark:text-stone-200 truncate">
              {node.name}
            </div>
            {expanded && dirSize > 0 && (
              <div className="text-12 text-stone-400 dark:text-stone-500 mt-0.5">
                {formatSize(dirSize)}
              </div>
            )}
          </div>
        </button>
        {hasDownloadableFiles && (
          <Tooltip content={t("project.exportZip")}>
            <ToolbarIconButton
              variant="muted"
              aria-label={`${t("project.exportZip")}: ${node.name}`}
              aria-busy={isDownloading}
              disabled={isDownloading}
              onClick={async () => {
                if (isDownloading) return;
                if (skippedCount > 0) {
                  toast.error(
                    `${t(
                      "chat.message.downloadFailed",
                      "下载失败",
                    )}: ${skippedPaths.join(", ")}`,
                  );
                  return;
                }
                try {
                  setIsDownloading(true);
                  await exportProjectZip({}, node.name, binaryFiles, {
                    failOnBinaryError: true,
                  });
                } catch (error) {
                  toast.error(
                    getDownloadFailureMessage(
                      t("chat.message.downloadFailed", "下载失败"),
                      error,
                    ),
                  );
                } finally {
                  setIsDownloading(false);
                }
              }}
              className="disabled:opacity-50 opacity-100 sm:[@media(hover:hover)_and_(pointer:fine)]:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
              icon={
                isDownloading ? (
                  <LoadingSpinner color="text-current" size={18} />
                ) : (
                  <Download size={18} />
                )
              }
            />
          </Tooltip>
        )}
        <Tooltip content={toggleLabel}>
          <ToolbarIconButton
            variant="muted"
            aria-expanded={expanded}
            aria-label={toggleLabel}
            onClick={toggleExpanded}
            icon={
              <ChevronRight
                size={18}
                className={clsx(
                  "transition-transform duration-200",
                  expanded && "rotate-90",
                )}
              />
            }
          />
        </Tooltip>
      </div>
      {expanded && (
        <div
          className={clsx("min-w-0 max-w-full", depth === 0 ? "pl-2" : "pl-4")}
        >
          {node.children.map((child, i) =>
            child.kind === "dir" ? (
              <TreeDirRow
                key={child.path || `d-${i}`}
                node={child}
                depth={depth + 1}
                defaultExpanded={defaultExpanded}
                onOpenPreview={onOpenPreview}
                onOpenImagePreview={onOpenImagePreview}
              />
            ) : (
              <TreeFileRow
                key={child.artifact.id}
                node={child}
                onOpenPreview={onOpenPreview}
                onOpenImagePreview={onOpenImagePreview}
              />
            ),
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Project row (non-file artifacts)                                   */
/* ------------------------------------------------------------------ */

function ProjectRow({
  artifact,
  onOpenPreview,
}: {
  artifact: RevealArtifact & { kind: "project" };
  onOpenPreview?: (
    preview: RevealPreviewRequest,
    source?: RevealPreviewOpenSource,
  ) => boolean;
}) {
  const { t } = useTranslation();
  const Icon = artifact.mode === "folder" ? FolderTree : Code2;
  const subtitle = `${t("project.fileCount", { count: artifact.fileCount })}${
    artifact.mode === "project" && artifact.template !== "static"
      ? ` · ${artifact.template}`
      : ""
  }`;

  return (
    <button
      type="button"
      onClick={() => onOpenPreview?.(artifact.preview, "manual")}
      className="group flex min-h-[60px] w-full cursor-pointer items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-theme-text/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)] motion-reduce:transition-none"
    >
      <span className="flex items-center justify-center size-8 shrink-0">
        <Icon
          size={24}
          strokeWidth={1.8}
          className="shrink-0 text-[var(--theme-primary)]"
        />
      </span>
      <span className="min-w-0 flex-1 text-left">
        <span className="block truncate text-14 leading-5 text-theme-text-secondary">
          {artifact.name}
        </span>
        <span className="mt-0.5 block truncate font-mono text-11 leading-4 text-theme-text-tertiary">
          {subtitle}
        </span>
      </span>
      <span className="flex size-8 shrink-0 items-center justify-center">
        <ChevronRight size={18} className="text-theme-text-tertiary" />
      </span>
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function getArtifactSubtitle(
  artifacts: RevealArtifact[],
  t: (key: string, opts?: Record<string, unknown>) => string,
) {
  const { fileCount, projectCount } = getRevealArtifactStats(artifacts);
  if (projectCount > 0 && fileCount > 0) {
    return t("chat.message.artifactsSubtitleMixed", {
      files: fileCount,
      projects: projectCount,
      defaultValue: "{{files}} 个文件 · {{projects}} 个项目",
    });
  }
  if (projectCount > 0) {
    return t("chat.message.artifactsSubtitleProjects", {
      count: projectCount,
      defaultValue: "{{count}} 个项目",
    });
  }
  return t("chat.message.artifactsSubtitleFiles", {
    count: fileCount,
    defaultValue: "{{count}} 个文件",
  });
}

function SectionTitle({
  children,
  count,
}: {
  children: ReactNode;
  count: number;
}) {
  return (
    <div className="flex items-center gap-2.5 px-3 pt-2 pb-1.5 font-serif">
      <span className="text-11 font-semibold uppercase tracking-wider text-[var(--theme-text-secondary)]">
        {children}
      </span>
      <span className="h-px flex-1 bg-gradient-to-r from-[var(--theme-border)]/80 to-transparent" />
      <span className="flex min-w-[20px] items-center justify-center rounded-full bg-[var(--theme-primary)]/10 px-1.5 py-0.5 text-10 font-bold tabular-nums text-[var(--theme-primary)]">
        {count}
      </span>
    </div>
  );
}

interface RevealArtifactImagePreviewItem {
  id: string;
  name: string;
  src: string;
}

function getRevealArtifactImagePreviewItems(
  artifacts: RevealArtifact[],
): RevealArtifactImagePreviewItem[] {
  return artifacts.flatMap((artifact) => {
    if (artifact.kind !== "file") return [];
    const ext = artifact.name.split(".").pop()?.toLowerCase() || "";
    const src = artifact.preview.imageUrl || artifact.preview.signedUrl;
    if (!src || !isImageFile(ext)) return [];
    return [{ id: artifact.id, name: artifact.name, src }];
  });
}

function DownloadAllButton({ artifacts }: { artifacts: RevealArtifact[] }) {
  const { t } = useTranslation();
  const [isDownloading, setIsDownloading] = useState(false);
  const { binaryFiles, skippedCount, skippedPaths } = useMemo(
    () => buildRevealArtifactBinaryFiles(artifacts),
    [artifacts],
  );

  if (Object.keys(binaryFiles).length === 0) return null;

  return (
    <Tooltip content={t("chat.message.downloadAll", "下载全部")}>
      <Button
        variant="ghost"
        size="sm"
        onClick={async () => {
          if (isDownloading) return;
          if (skippedCount > 0) {
            toast.error(
              `${t(
                "chat.message.downloadFailed",
                "下载失败",
              )}: ${skippedPaths.join(", ")}`,
            );
            return;
          }
          try {
            setIsDownloading(true);
            await exportProjectZip(
              {},
              t("chat.message.allFiles", "全部文件"),
              binaryFiles,
              { failOnBinaryError: true },
            );
          } catch (error) {
            toast.error(
              getDownloadFailureMessage(
                t("chat.message.downloadFailed", "下载失败"),
                error,
              ),
            );
          } finally {
            setIsDownloading(false);
          }
        }}
        disabled={isDownloading}
        aria-busy={isDownloading}
        aria-label={t("chat.message.downloadAll", "下载全部")}
        className="!min-h-[44px] sm:!min-h-0 text-11"
      >
        {isDownloading ? (
          <LoadingSpinner size={12} color="text-current" />
        ) : (
          <Download size={12} />
        )}
        <span className="reveal-artifacts-download-label">
          {t("chat.message.downloadAll", "下载全部")}
        </span>
      </Button>
    </Tooltip>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export function RevealArtifactsSummary({
  parts,
  isStreaming,
  onOpenPreview,
}: {
  parts?: MessagePart[];
  isStreaming?: boolean;
  onOpenPreview?: (
    preview: RevealPreviewRequest,
    source?: RevealPreviewOpenSource,
  ) => boolean;
}) {
  const { t } = useTranslation();
  const artifacts = useMemo(() => collectRevealArtifacts(parts), [parts]);
  const subtitle = getArtifactSubtitle(artifacts, t);
  const [expanded, setExpanded] = useState(false);
  const disclosureId = useId();
  const stats = useMemo(() => getRevealArtifactStats(artifacts), [artifacts]);
  const [activeImagePreviewId, setActiveImagePreviewId] = useState<
    string | null
  >(null);

  const fileTree = useMemo(
    () =>
      buildRevealArtifactTree(
        artifacts.filter(
          (a): a is RevealArtifact & { kind: "file" } => a.kind === "file",
        ),
      ),
    [artifacts],
  );
  const projects = useMemo(
    () =>
      artifacts.filter(
        (a): a is RevealArtifact & { kind: "project" } => a.kind === "project",
      ),
    [artifacts],
  );
  const imagePreviewItems = useMemo(
    () => getRevealArtifactImagePreviewItems(artifacts),
    [artifacts],
  );
  const activeImageIndex = activeImagePreviewId
    ? imagePreviewItems.findIndex((item) => item.id === activeImagePreviewId)
    : -1;
  const activeImageItem =
    activeImageIndex >= 0 ? imagePreviewItems[activeImageIndex] : null;
  const previousImageItem =
    activeImageIndex > 0 ? imagePreviewItems[activeImageIndex - 1] : null;
  const nextImageItem =
    activeImageIndex >= 0 && activeImageIndex < imagePreviewItems.length - 1
      ? imagePreviewItems[activeImageIndex + 1]
      : null;
  const imagePositionLabel =
    activeImageIndex >= 0 && imagePreviewItems.length > 1
      ? `${activeImageIndex + 1} / ${imagePreviewItems.length}`
      : undefined;

  const handleOpenImagePreview = useCallback(
    (artifact: RevealArtifact & { kind: "file" }) => {
      setActiveImagePreviewId(artifact.id);
    },
    [],
  );
  const handlePreviousImage = useCallback(() => {
    if (previousImageItem) {
      setActiveImagePreviewId(previousImageItem.id);
    }
  }, [previousImageItem]);
  const handleNextImage = useCallback(() => {
    if (nextImageItem) {
      setActiveImagePreviewId(nextImageItem.id);
    }
  }, [nextImageItem]);

  if (isStreaming || artifacts.length === 0) {
    return null;
  }

  const useSidePanel = artifacts.length >= 4;
  const collapsedNames = artifacts.slice(0, 2).map((artifact) => artifact.name).join(" · ");

  const handleOpenPanel = () => {
    openPersistentToolPanel({
      title: t("chat.message.allFiles", "全部文件"),
      icon: <FolderTree size={16} />,
      status: "idle",
      subtitle,
      panelKey: "reveal-artifacts",
      mobileFillViewport: true,
      customHeader: (
        <div className="tool-console-header flex min-w-0 shrink-0 items-center justify-between gap-2 px-2 py-1.5 sm:px-4 sm:py-2">
          <span className="min-w-0 truncate text-12 text-theme-text-tertiary">
            {t("chat.message.fileDirectory", "文件目录")}
          </span>
          <DownloadAllButton artifacts={artifacts} />
        </div>
      ),
      children: (
        <div className="flex min-h-full flex-col bg-[var(--theme-bg-card)]">
          <div className="min-w-0 max-w-full flex-1 overflow-x-hidden overflow-y-auto p-1.5">
            {projects.length > 0 && (
              <section>
                {fileTree.children.length > 0 && (
                  <SectionTitle count={projects.length}>
                    {t("chat.message.projects", "项目")}
                  </SectionTitle>
                )}
                <div className="space-y-1.5">
                  {projects.map((p) => (
                    <ProjectRow
                      key={p.id}
                      artifact={p}
                      onOpenPreview={onOpenPreview}
                    />
                  ))}
                </div>
              </section>
            )}
            {fileTree.children.length > 0 && (
              <section>
                {projects.length > 0 && (
                  <SectionTitle count={stats.fileCount}>
                    {t("chat.message.files", "文件")}
                  </SectionTitle>
                )}
                <div>
                  {fileTree.children.map((child, i) =>
                    child.kind === "dir" ? (
                      <TreeDirRow
                        key={child.path || `d-${i}`}
                        node={child}
                        depth={0}
                        defaultExpanded={false}
                        onOpenPreview={onOpenPreview}
                        onOpenImagePreview={handleOpenImagePreview}
                      />
                    ) : (
                      <TreeFileRow
                        key={child.artifact.id}
                        node={child}
                        onOpenPreview={onOpenPreview}
                        onOpenImagePreview={handleOpenImagePreview}
                      />
                    ),
                  )}
                </div>
              </section>
            )}
          </div>
        </div>
      ),
    });
  };

  return (
    <>
      <section className="reveal-artifacts-summary my-2 w-full min-w-0 sm:my-3" aria-label={subtitle}>
        <div className="w-full min-w-0 overflow-hidden rounded-xl border border-[var(--theme-border)] bg-theme-text/[0.02]">
          {artifacts.length > 1 && (
            <div className="relative">
              <button
                type="button"
                aria-label={useSidePanel ? t("chat.message.allFiles", "全部文件") : subtitle}
                aria-expanded={useSidePanel ? undefined : expanded}
                aria-controls={useSidePanel ? undefined : disclosureId}
                onClick={useSidePanel ? handleOpenPanel : () => setExpanded(!expanded)}
                className="reveal-artifacts-toggle flex min-h-[52px] w-full items-center gap-3 pl-3 pr-40 py-2 text-left hover:bg-theme-text/[0.04] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--theme-primary)] motion-reduce:transition-none"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center">
                  <FolderIcon size={24} className="shrink-0" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-13 text-theme-text-secondary">{subtitle}</span>
                  {(useSidePanel || !expanded) && (
                    <span className="mt-0.5 block truncate text-12 text-theme-text-tertiary">{collapsedNames}</span>
                  )}
                </span>
                <span className="absolute right-3 flex h-8 w-8 items-center justify-center">
                {useSidePanel ? (
                  <ChevronRight size={16} className="shrink-0 text-theme-text-tertiary" />
                ) : (
                  <ChevronDown
                    size={16}
                    className={clsx(
                      "shrink-0 text-theme-text-tertiary transition-transform motion-reduce:transition-none",
                      expanded && "rotate-180",
                    )}
                  />
                )}
                </span>
              </button>
              <div className="absolute right-12 top-1/2 -translate-y-1/2">
                <DownloadAllButton artifacts={artifacts} />
              </div>
            </div>
          )}
          {!useSidePanel && (artifacts.length === 1 || expanded) && (
            <div
              id={disclosureId}
              className={clsx("divide-y divide-[var(--theme-border)]", artifacts.length > 1 && "border-t border-[var(--theme-border)]")}
            >
              {artifacts.map((artifact) =>
                artifact.kind === "file" ? (
                  <TreeFileRow
                    key={artifact.id}
                    node={{ kind: "file", artifact }}
                    inline
                    onOpenPreview={onOpenPreview}
                    onOpenImagePreview={handleOpenImagePreview}
                  />
                ) : (
                  <ProjectRow
                    key={artifact.id}
                    artifact={artifact}
                    onOpenPreview={onOpenPreview}
                  />
                ),
              )}
            </div>
          )}
        </div>
      </section>
      {activeImageItem && (
        <ImageViewer
          src={activeImageItem.src}
          alt={activeImageItem.name}
          isOpen={!!activeImageItem}
          onClose={() => setActiveImagePreviewId(null)}
          onPrevious={handlePreviousImage}
          onNext={handleNextImage}
          hasPrevious={!!previousImageItem}
          hasNext={!!nextImageItem}
          positionLabel={imagePositionLabel}
        />
      )}
    </>
  );
}
