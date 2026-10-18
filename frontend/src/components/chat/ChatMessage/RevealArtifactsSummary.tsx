import { InteractiveIcon } from "../../common/InteractiveIcon";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { type ReactNode, useCallback, useId, useMemo, useState } from "react";
import {
  FolderTree,
  Folder as FolderIcon,
  FolderOpen,
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
import { FileIcon } from "../../common/FileIcon";
import { ImageWithSkeleton } from "./ImageWithSkeleton";
import { exportProjectZip } from "../../../utils/exportProjectZip";

/* ------------------------------------------------------------------ */
/*  Tree renderer                                                      */
/* ------------------------------------------------------------------ */

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
  return (
    <span className="size-10 shrink-0 overflow-hidden rounded-lg ring-1 ring-stone-200/60 dark:ring-stone-700/50">
      <FileIcon
        icon={info.icon}
        bg="bg-theme-bg-subtle"
        color={info.color}
        iconSize={16}
        strokeWidth={1.8}
      />
    </span>
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

  return (
    <div
      data-inline-attachment={inline || undefined}
      className={clsx(
        "group flex min-w-0 max-w-full items-center gap-1 w-full transition-colors motion-reduce:transition-none",
        inline
          ? "px-3 py-2 hover:bg-theme-bg-hover"
          : "rounded-xl px-3 py-2.5 hover:bg-theme-bg-hover",
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
              className={
                inline
                  ? "flex h-10 w-10 shrink-0 items-center justify-center"
                  : "contents"
              }
            >
              <ImageWithSkeleton
                src={imageSrc}
                alt={node.artifact.name}
                skipUrlResolve
                inline
                className={clsx(
                  inline ? "w-10 h-10" : "w-9 h-9",
                  "rounded-lg object-cover shrink-0 bg-theme-bg-subtle dark:bg-stone-800",
                )}
              />
            </span>
          ) : (
            getFileIcon(node.artifact.name)
          )}
          <div className="flex-1 min-w-0 text-left">
            <div
              className={clsx(
                "text-14 font-medium text-theme-text",
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
                "text-12",
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
  const FolderStateIcon = expanded ? FolderOpen : FolderIcon;
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
      <div className="flex min-w-0 max-w-full w-full items-center gap-3 overflow-hidden px-3 py-2.5 rounded-xl hover:bg-theme-bg-hover dark:hover:bg-theme-bg-hover transition-colors group">
        <button
          type="button"
          aria-expanded={expanded}
          onClick={toggleExpanded}
          className="flex !min-w-0 min-h-[44px] flex-1 items-center gap-3 text-left rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)]"
        >
          <span className="flex size-10 shrink-0 items-center justify-center">
            <InteractiveIcon>
              <FolderStateIcon size={16} className="shrink-0" />
            </InteractiveIcon>
          </span>
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
      className="group flex min-h-[60px] w-full cursor-pointer items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-theme-bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)] motion-reduce:transition-none"
    >
      <span className="flex items-center justify-center size-10 rounded-lg bg-theme-bg-subtle shrink-0">
        <InteractiveIcon>
          <Icon
            size={24}
            strokeWidth={1.8}
            className="shrink-0 text-[var(--theme-primary)]"
          />
        </InteractiveIcon>
      </span>
      <span className="min-w-0 flex-1 text-left">
        <span className="block truncate text-14 font-medium leading-5 text-theme-text">
          {artifact.name}
        </span>
        <span className="mt-0.5 block truncate text-12 leading-4 text-theme-text-tertiary">
          {subtitle}
        </span>
      </span>
      <span className="flex size-8 shrink-0 items-center justify-center">
        <InteractiveIcon>
          <ChevronRight size={18} className="text-theme-text-tertiary" />
        </InteractiveIcon>
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
    <div className="flex items-center gap-2 px-3 pt-2 pb-1.5 font-serif">
      <span className="text-11 font-semibold uppercase tracking-wider text-[var(--theme-text-secondary)]">
        {children}
      </span>
      <span className="h-px flex-1 bg-linear-to-r from-[var(--theme-border)]/80 to-transparent" />
      <span className="count-badge">{Math.min(count, 99)}</span>
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
  const FolderStateIcon = !useSidePanel && expanded ? FolderOpen : FolderIcon;
  const collapsedNames = artifacts
    .slice(0, 2)
    .map((artifact) => artifact.name)
    .join(" · ");

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
      <section
        className="reveal-artifacts-summary w-full min-w-0"
        aria-label={subtitle}
      >
        <div className="message-artifact-card w-full min-w-0 overflow-hidden">
          {artifacts.length > 1 && (
            <div className="relative">
              <button
                type="button"
                aria-label={
                  useSidePanel
                    ? t("chat.message.allFiles", "全部文件")
                    : subtitle
                }
                aria-expanded={useSidePanel ? undefined : expanded}
                aria-controls={useSidePanel ? undefined : disclosureId}
                onClick={
                  useSidePanel ? handleOpenPanel : () => setExpanded(!expanded)
                }
                className="reveal-artifacts-toggle flex min-h-[60px] w-full items-center gap-3 pl-3 pr-40 py-2 text-left hover:bg-theme-bg-hover transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--theme-primary)] motion-reduce:transition-none"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-theme-bg-subtle text-theme-text-secondary">
                  <InteractiveIcon>
                    <FolderStateIcon
                      size={16}
                      strokeWidth={1.8}
                      className="shrink-0"
                    />
                  </InteractiveIcon>
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-13 text-theme-text-secondary">
                    {subtitle}
                  </span>
                  {(useSidePanel || !expanded) && (
                    <span className="mt-0.5 block truncate text-12 text-theme-text-tertiary">
                      {collapsedNames}
                    </span>
                  )}
                </span>
                <span className="absolute right-3 flex h-8 w-8 items-center justify-center">
                  {useSidePanel ? (
                    <InteractiveIcon>
                      <ChevronRight
                        size={16}
                        className="shrink-0 text-theme-text-tertiary"
                      />
                    </InteractiveIcon>
                  ) : (
                    <InteractiveIcon>
                      <ChevronDown
                        size={16}
                        className={clsx(
                          "shrink-0 text-theme-text-tertiary transition-transform motion-reduce:transition-none",
                          expanded && "rotate-180",
                        )}
                      />
                    </InteractiveIcon>
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
              className={clsx(
                "divide-y divide-[var(--theme-border)]",
                artifacts.length > 1 && "border-t border-[var(--theme-border)]",
              )}
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
