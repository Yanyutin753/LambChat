import { useCallback, useMemo, useState } from "react";
import { Download, ChevronRight, Loader2 } from "lucide-react";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { getFileTypeInfo, isImageFile } from "../../../documents/utils";
import { exportProjectZip } from "../../../../utils/exportProjectZip";
import toast from "react-hot-toast";
import { CopyButton } from "../../../common/CopyButton";
import { Button, ToolbarIconButton } from "../../../common/ui";
import { countProjectRevealFiles } from "./projectRevealState";
import { ImageWithSkeleton } from "../ImageWithSkeleton";
import { Tooltip } from "../../../common/Tooltip";

export interface TreeNode {
  name: string;
  path: string;
  isDir: boolean;
  children: TreeNode[];
  size?: number;
  isBinary?: boolean;
  url?: string;
}

function buildFileTree(
  files: Record<string, string>,
  binaryFiles: Record<string, string>,
): TreeNode {
  const root: TreeNode = { name: "", path: "", isDir: true, children: [] };
  const allPaths = [...Object.keys(files), ...Object.keys(binaryFiles)].sort();
  for (const filePath of allPaths) {
    const parts = filePath.replace(/^\//, "").split("/").filter(Boolean);
    let current = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isFile = i === parts.length - 1;
      const childPath = "/" + parts.slice(0, i + 1).join("/");
      let child = current.children.find((c) => c.name === part);
      if (!child) {
        const isBinary = isFile && Object.hasOwn(binaryFiles, filePath);
        child = {
          name: part,
          path: isFile ? filePath : childPath,
          isDir: !isFile,
          children: [],
          size:
            isFile && !isBinary
              ? new TextEncoder().encode(files[filePath] ?? "").byteLength
              : undefined,
          isBinary,
          url: isBinary ? binaryFiles[filePath] : undefined,
        };
        current.children.push(child);
      }
      current = child;
    }
  }
  sortTree(root);
  return root;
}

function sortTree(node: TreeNode) {
  node.children.sort((a, b) => {
    if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  for (const child of node.children) {
    if (child.isDir) sortTree(child);
  }
}

const FILE_ICON_SIZE = 36;

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

function getFileIcon(name: string) {
  const info = getFileTypeInfo(name);
  const Icon = info.icon;
  return (
    <Icon size={FILE_ICON_SIZE} className={clsx("shrink-0", info.color)} />
  );
}

function formatSize(bytes?: number): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function downloadFile(
  name: string,
  content: string,
  isBinary = false,
  url?: string,
) {
  if (isBinary && url) {
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    return;
  }
  const blob = new Blob([content], { type: "text/plain" });
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  a.click();
  URL.revokeObjectURL(href);
}

function collectSubtreeFiles(
  node: TreeNode,
  files: Record<string, string>,
): { textFiles: Record<string, string>; binFiles: Record<string, string> } {
  const textFiles: Record<string, string> = {};
  const binFiles: Record<string, string> = {};
  const walk = (n: TreeNode) => {
    if (!n.isDir) {
      if (n.isBinary && n.url) {
        binFiles[n.path] = n.url;
      } else if (files[n.path] != null) {
        textFiles[n.path] = files[n.path];
      }
      return;
    }
    n.children.forEach(walk);
  };
  walk(node);
  return { textFiles, binFiles };
}

function FileTreeNode({
  node,
  files,
  depth,
  expandedDirs,
  toggleDir,
  onFileClick,
}: {
  node: TreeNode;
  files: Record<string, string>;
  depth: number;
  expandedDirs: Set<string>;
  toggleDir: (path: string, expanded: boolean) => void;
  onFileClick?: (node: TreeNode) => void;
}) {
  const { t } = useTranslation();
  const [isDownloading, setIsDownloading] = useState(false);
  const { textFiles, binFiles } = useMemo(
    () => collectSubtreeFiles(node, files),
    [node, files],
  );
  if (node.isDir) {
    const expanded = expandedDirs.has(node.path);
    const dirSize = expanded
      ? node.children.reduce((sum, c) => sum + (c.size || 0), 0)
      : 0;
    const hasFiles =
      Object.keys(textFiles).length + Object.keys(binFiles).length > 0;
    return (
      <div className="min-w-0 max-w-full">
        <div className="group flex min-w-0 max-w-full items-center gap-1 w-full px-3 py-2.5 rounded-xl hover:bg-theme-bg-subtle transition-colors">
          <Tooltip content={node.name}>
            <button
              type="button"
              onClick={() => toggleDir(node.path, !expanded)}
              aria-expanded={expanded}
              data-sidebar-snapshot-key={`file-tree:${node.path}`}
              aria-label={node.name}
              className="flex min-w-0 min-h-[44px] flex-1 items-center gap-3 text-left rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)]"
            >
              <FolderIcon size={36} className="shrink-0" />
              <div className="flex-1 min-w-0 text-left">
                <div className="text-14 font-medium text-theme-text truncate">
                  {node.name}
                </div>
                {expanded && dirSize > 0 && (
                  <div className="text-12 text-theme-text-tertiary mt-0.5">
                    {formatSize(dirSize)}
                  </div>
                )}
              </div>
            </button>
          </Tooltip>
          {hasFiles && (
            <Tooltip content={t("project.downloadFolder")}>
              <ToolbarIconButton
                variant="muted"
                disabled={isDownloading}
                aria-busy={isDownloading}
                aria-label={`${t("project.downloadFolder")}: ${node.name}`}
                onClick={async () => {
                  if (isDownloading) return;
                  try {
                    setIsDownloading(true);
                    await exportProjectZip(textFiles, node.name, binFiles, {
                      failOnBinaryError: true,
                    });
                  } catch {
                    toast.error(t("chat.message.downloadFailed"));
                  } finally {
                    setIsDownloading(false);
                  }
                }}
                className="disabled:opacity-50 opacity-100 sm:[@media(hover:hover)_and_(pointer:fine)]:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
                icon={
                  isDownloading ? (
                    <Loader2 size={18} className="animate-spin" />
                  ) : (
                    <Download size={18} />
                  )
                }
              />
            </Tooltip>
          )}
          <ToolbarIconButton
            variant="muted"
            aria-label={`${t(expanded ? "common.collapse" : "common.expand")}: ${node.name}`}
            aria-expanded={expanded}
            onClick={() => toggleDir(node.path, !expanded)}
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
        </div>
        {expanded && (
          <div
            className={clsx(
              "min-w-0 max-w-full",
              depth === 0 ? "pl-2" : "pl-4",
            )}
          >
            {node.children.map((child) => (
              <FileTreeNode
                key={child.path}
                node={child}
                files={files}
                depth={depth + 1}
                expandedDirs={expandedDirs}
                toggleDir={toggleDir}
                onFileClick={onFileClick}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  const ext = node.name.split(".").pop()?.toLowerCase() || "";
  const imageSrc = isImageFile(ext)
    ? node.isBinary && node.url
      ? node.url
      : !node.isBinary && files[node.path]
        ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
            files[node.path],
          )}`
        : null
    : null;

  return (
    <div className="group flex min-w-0 max-w-full items-center gap-1 w-full px-3 py-2.5 rounded-xl hover:bg-theme-bg-subtle transition-colors">
      <Tooltip content={node.name}>
        <button
          type="button"
          aria-label={node.name}
          onClick={() => onFileClick?.(node)}
          className="flex min-w-0 min-h-[44px] flex-1 items-center gap-3 text-left cursor-pointer rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)]"
        >
          {imageSrc ? (
            <ImageWithSkeleton
              src={imageSrc}
              alt={node.name}
              skipUrlResolve
              inline
              className="w-9 h-9 rounded-lg object-cover shrink-0 bg-theme-bg-subtle"
            />
          ) : (
            getFileIcon(node.name)
          )}
          <div className="flex-1 min-w-0 text-left">
            <div className="text-14 text-theme-text-secondary line-clamp-2 break-all text-balance">
              {node.name}
            </div>
            <div className="text-12 text-theme-text-tertiary mt-0.5">
              {node.isBinary ? t("documents.binary") : formatSize(node.size)}
            </div>
          </div>
        </button>
      </Tooltip>
      <div className="flex shrink-0 items-center gap-1 opacity-100 sm:[@media(hover:hover)_and_(pointer:fine)]:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
        <Tooltip content={t("documents.downloadFile")}>
          <ToolbarIconButton
            variant="muted"
            disabled={node.isBinary ? !node.url : files[node.path] == null}
            aria-label={`${t("documents.downloadFile")}: ${node.name}`}
            onClick={() => {
              downloadFile(
                node.name,
                files[node.path] || "",
                node.isBinary,
                node.url,
              );
            }}
            icon={<Download size={18} />}
          />
        </Tooltip>
        {!node.isBinary && files[node.path] != null && (
          <CopyButton text={files[node.path]} size={18} />
        )}
      </div>
    </div>
  );
}

export function FileTreeView({
  files,
  binaryFiles,
  projectName,
  onFileClick,
  showHeader = true,
}: {
  files: Record<string, string>;
  binaryFiles: Record<string, string>;
  projectName?: string;
  onFileClick?: (node: TreeNode) => void;
  showHeader?: boolean;
}) {
  const { t } = useTranslation();
  const [isDownloading, setIsDownloading] = useState(false);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(
    () => new Set(),
  );

  const tree = useMemo(
    () => buildFileTree(files, binaryFiles),
    [files, binaryFiles],
  );
  const fileCount = useMemo(
    () => countProjectRevealFiles(files, binaryFiles),
    [files, binaryFiles],
  );

  const toggleDir = useCallback((path: string, expanded: boolean) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (expanded) next.add(path);
      else next.delete(path);
      return next;
    });
  }, []);

  return (
    <div className="flex min-h-0 min-w-0 max-w-full flex-col h-full bg-theme-bg-card">
      {showHeader && (
        <div className="flex items-center justify-between px-3 py-2 border-b border-theme-border shrink-0">
          <span className="text-12 text-theme-text-tertiary">
            {t("project.fileCount", "{{count}} 个文件", {
              count: fileCount,
            })}
          </span>
          <Button
            variant="ghost"
            size="sm"
            loading={isDownloading}
            aria-busy={isDownloading}
            onClick={async () => {
              if (isDownloading) return;
              try {
                setIsDownloading(true);
                await exportProjectZip(
                  files,
                  projectName || "project",
                  binaryFiles,
                  { failOnBinaryError: true },
                );
              } catch {
                toast.error(t("chat.message.downloadFailed"));
              } finally {
                setIsDownloading(false);
              }
            }}
            className="!min-h-[44px] sm:!min-h-0 text-12"
          >
            <Download size={16} />
            {t("project.exportZip")}
          </Button>
        </div>
      )}
      <div className="min-h-0 min-w-0 max-w-full flex-1 overflow-x-hidden overflow-y-auto p-1.5">
        {tree.children.map((child) => (
          <FileTreeNode
            key={child.path}
            node={child}
            files={files}
            depth={0}
            expandedDirs={expandedDirs}
            toggleDir={toggleDir}
            onFileClick={onFileClick}
          />
        ))}
      </div>
    </div>
  );
}
