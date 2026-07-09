import { type ReactNode, useCallback, useMemo, useState } from "react";
import { FolderTree, Code2, ChevronRight, Download, Copy } from "lucide-react";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import type { MessagePart } from "../../../types";
import { getFileTypeInfo, isImageFile } from "../../documents/utils";
import { ImageViewer } from "../../common";
import { openPersistentToolPanel } from "./items/persistentToolPanelState";
import type { RevealPreviewOpenSource } from "./items/revealPreviewState";
import type { RevealPreviewRequest } from "./items/revealPreviewData";
import {
  buildRevealArtifactTree,
  collectRevealArtifacts,
  getRevealArtifactStats,
  type RevealArtifact,
  type RevealArtifactTreeDir,
  type RevealArtifactTreeFile,
} from "./revealArtifacts";
import { ImageWithSkeleton } from "./ImageWithSkeleton";
import { copyToClipboard } from "../../../utils/clipboard";

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

const FILE_ICON_SIZE = 36;

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

function getTreeDirSize(node: RevealArtifactTreeDir): number {
  return node.children.reduce((sum, child) => {
    if (child.kind === "file") {
      return sum + (child.artifact.fileSize || 0);
    }
    return sum + getTreeDirSize(child);
  }, 0);
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
}: {
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
    <button
      type="button"
      onClick={() => {
        if (imageSrc && onOpenImagePreview) {
          onOpenImagePreview(node.artifact);
          return;
        }
        onOpenPreview?.(node.artifact.preview, "manual");
      }}
      className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl hover:bg-stone-50 dark:hover:bg-stone-800/60 transition-colors group cursor-pointer"
    >
      {imageSrc ? (
        <ImageWithSkeleton
          src={imageSrc}
          alt={node.artifact.name}
          skipUrlResolve
          inline
          className="w-9 h-9 rounded-lg object-cover shrink-0 bg-stone-100 dark:bg-stone-800"
        />
      ) : (
        getFileIcon(node.artifact.name)
      )}
      <div className="flex-1 min-w-0 text-left">
        <div className="text-sm text-stone-700 dark:text-stone-300 truncate">
          {node.artifact.name}
        </div>
        <div className="text-xs text-stone-400 dark:text-stone-500 mt-0.5">
          {node.artifact.fileSize
            ? formatSize(node.artifact.fileSize)
            : node.artifact.description || node.artifact.path}
        </div>
      </div>
      <span
        onClick={(e) => {
          e.stopPropagation();
          downloadFile(node.artifact.name, node.artifact.preview.signedUrl);
        }}
        className="shrink-0 p-1.5 rounded-lg text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-700 opacity-0 group-hover:opacity-100 transition-all"
        title={t("project.exportZip")}
      >
        <Download size={20} />
      </span>
      <span
        onClick={(e) => {
          e.stopPropagation();
          copyToClipboard(
            node.artifact.preview.signedUrl || node.artifact.path,
          );
        }}
        className="shrink-0 p-1.5 rounded-lg text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-700 opacity-0 group-hover:opacity-100 transition-all"
        title={t("chat.message.copy")}
      >
        <Copy size={20} />
      </span>
    </button>
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
  const [expanded, setExpanded] = useState(defaultExpanded ?? false);
  const dirSize = expanded ? getTreeDirSize(node) : 0;

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl hover:bg-stone-50 dark:hover:bg-stone-800/60 transition-colors"
      >
        <FolderIcon size={36} className="shrink-0" />
        <div className="flex-1 min-w-0 text-left">
          <div className="text-sm font-medium text-stone-800 dark:text-stone-200 truncate">
            {node.name}
          </div>
          {expanded && dirSize > 0 && (
            <div className="text-xs text-stone-400 dark:text-stone-500 mt-0.5">
              {formatSize(dirSize)}
            </div>
          )}
        </div>
        <ChevronRight
          size={18}
          className={clsx(
            "shrink-0 text-stone-400 transition-transform duration-200",
            expanded && "rotate-90",
          )}
        />
      </button>
      {expanded && (
        <div className={clsx(depth === 0 ? "pl-2" : "pl-4")}>
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
      className="group flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-[var(--theme-bg-subtle)]"
    >
      <span className="flex items-center justify-center size-10 rounded-xl shrink-0 bg-[var(--theme-primary-light)] transition-transform duration-200 group-hover:scale-105">
        <Icon
          size={20}
          strokeWidth={1.8}
          className="shrink-0 text-[var(--theme-primary)]"
        />
      </span>
      <span className="min-w-0 flex-1 text-left">
        <span className="block truncate text-sm font-medium leading-5 text-[var(--theme-text)]">
          {artifact.name}
        </span>
        <span className="mt-0.5 block truncate text-xs leading-4 text-[var(--theme-text-secondary)]">
          {subtitle}
        </span>
      </span>
      <ChevronRight
        size={18}
        className="shrink-0 text-[var(--theme-text-secondary)] transition-transform duration-200"
      />
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
    <div className="flex items-center gap-2.5 px-3 pt-2 pb-1.5">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--theme-text-secondary)]">
        {children}
      </span>
      <span className="h-px flex-1 bg-gradient-to-r from-[var(--theme-border)]/80 to-transparent" />
      <span className="flex min-w-[20px] items-center justify-center rounded-full bg-[var(--theme-primary)]/10 px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-[var(--theme-primary)]">
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

  const handleOpenPanel = () => {
    openPersistentToolPanel({
      title: t("chat.message.allFiles", "全部文件"),
      icon: <FolderTree size={16} />,
      status: "idle",
      subtitle,
      panelKey: "reveal-artifacts",
      mobileFillViewport: true,
      children: (
        <div className="flex min-h-full flex-col bg-[var(--theme-bg-card)]">
          <div className="shrink-0 border-b border-[var(--theme-border)] bg-gradient-to-b from-[var(--theme-bg)] to-[var(--theme-bg-card)] px-4 py-2">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] font-medium text-[var(--theme-text-secondary)]">
                {subtitle}
              </span>
              <span className="shrink-0 rounded-md bg-[var(--theme-primary)]/10 px-2 py-0.5 text-[11px] font-bold tabular-nums text-[var(--theme-primary)]">
                {stats.totalCount}
              </span>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-1.5">
            {projects.length > 0 && (
              <section>
                <SectionTitle count={projects.length}>
                  {t("chat.message.projects", "项目")}
                </SectionTitle>
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
                <SectionTitle count={stats.fileCount}>
                  {t("chat.message.files", "文件")}
                </SectionTitle>
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
      <section className="my-2 sm:my-3 min-w-0">
        <div
          role="button"
          tabIndex={0}
          onClick={handleOpenPanel}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              handleOpenPanel();
            }
          }}
          className="group flex cursor-pointer items-center gap-3 rounded-2xl bg-[var(--theme-bg-card)] px-3 py-2.5 shadow-[0_1px_3px_var(--theme-shadow-sm)] ring-1 ring-[var(--theme-border)] transition-all duration-200 hover:shadow-[0_4px_12px_var(--theme-shadow-md)] hover:ring-[var(--theme-text-secondary)]/20 sm:px-4 sm:py-3"
        >
          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[var(--theme-primary-light)] transition-transform duration-200 group-hover:scale-105">
            <FolderIcon size={28} className="shrink-0" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold text-[var(--theme-text)]">
              {t("chat.message.allFiles", "全部文件")}
            </div>
            <div className="mt-0.5 truncate text-xs text-[var(--theme-text-secondary)]">
              {subtitle}
            </div>
          </div>
          <div className="relative z-10 flex shrink-0 items-center gap-1">
            <span className="rounded-lg bg-[var(--theme-primary-light)] px-3 py-1.5 text-xs font-medium text-[var(--theme-primary)] ring-1 ring-[var(--theme-border)] transition-colors group-hover:bg-[var(--theme-primary)]/15 group-hover:ring-[var(--theme-text-secondary)]/20">
              {t("project.preview", "预览")}
            </span>
          </div>
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
