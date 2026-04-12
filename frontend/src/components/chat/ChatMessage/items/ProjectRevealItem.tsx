import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { Code2, FolderTree, Download, Maximize, X } from "lucide-react";
import { PreviewHeader } from "../../../common/FileIcon";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { LoadingSpinner } from "../../../common";
import ProjectPreview from "../../../documents/previews/ProjectPreview";
import { exportProjectZip } from "../../../../utils/exportProjectZip";
import { getFullUrl } from "../../../../services/api/config";
import { rewriteProjectTextFiles } from "./projectRevealAssetUtils";
import { closeCurrentToolPanel } from "./ToolResultPanel";

// v1 格式（旧后端）
interface ProjectRevealResultV1 {
  type: "project_reveal";
  name: string;
  description?: string;
  template:
    | "react"
    | "vue"
    | "vanilla"
    | "static"
    | "angular"
    | "svelte"
    | "solid"
    | "nextjs";
  files: Record<string, string>;
  entry?: string;
  path?: string;
  file_count?: number;
  error?: string;
  message?: string;
}

// v2 格式（新后端，所有文件上传到 OSS）
interface FileManifestEntry {
  url: string;
  is_binary: boolean;
  size: number;
  content_type?: string;
}

interface ProjectRevealResultV2 {
  type: "project_reveal";
  version: 2;
  name: string;
  description?: string;
  template:
    | "react"
    | "vue"
    | "vanilla"
    | "static"
    | "angular"
    | "svelte"
    | "solid"
    | "nextjs";
  files: Record<string, FileManifestEntry>;
  entry?: string;
  path?: string;
  file_count?: number;
  error?: string;
  message?: string;
}

type ProjectRevealResult = ProjectRevealResultV1 | ProjectRevealResultV2;

function isV2(result: ProjectRevealResult): result is ProjectRevealResultV2 {
  if ("version" in result && result.version === 2) return true;
  // 也通过 files 的值类型判断
  const firstFile = Object.values(result.files)[0];
  return (
    typeof firstFile === "object" && firstFile !== null && "url" in firstFile
  );
}

/**
 * 从 OSS 并行获取所有文本文件内容
 */
async function fetchTextFiles(
  textFileEntries: Array<[string, FileManifestEntry]>,
): Promise<{ files: Record<string, string>; failed: string[] }> {
  const entries = await Promise.all(
    textFileEntries.map(
      async ([path, entry]): Promise<[string, string] | null> => {
        try {
          const fullUrl = getFullUrl(entry.url) || entry.url;
          const resp = await fetch(fullUrl);
          if (!resp.ok) {
            console.warn(
              `[reveal_project] Failed to fetch ${path}: ${resp.status}`,
            );
            return null;
          }
          const text = await resp.text();
          return [path, text];
        } catch (e) {
          console.warn(`[reveal_project] Error fetching ${path}:`, e);
          return null;
        }
      },
    ),
  );

  const files: Record<string, string> = {};
  const failed: string[] = [];
  for (const entry of entries) {
    if (entry) {
      files[entry[0]] = entry[1];
    }
  }
  // 找出哪些文件没加载成功
  for (const [path] of textFileEntries) {
    if (!(path in files)) {
      failed.push(path);
    }
  }
  return { files, failed };
}

export function ProjectRevealItem({
  args,
  result,
  success,
  isPending,
  cancelled,
}: {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
}) {
  const { t } = useTranslation();
  const [showFullPreview, setShowFullPreview] = useState(false);
  const [viewMode, setViewMode] = useState<"center" | "sidebar">("sidebar");
  const sidebarWidthRef = useRef(
    parseInt(localStorage.getItem("sidebar-preview-width") || "45", 10),
  );
  const isResizing = useRef(false);
  const justResized = useRef(false);

  // Set CSS variable for sidebar width
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty(
      "--sidebar-preview-width",
      `${sidebarWidthRef.current}%`,
    );
  }, []);

  // Signal the main layout to compress when sidebar is open
  useEffect(() => {
    if (!showFullPreview) return;
    const root = document.documentElement;
    if (viewMode === "sidebar") {
      root.setAttribute("data-sidebar-preview", "open");
    } else {
      root.removeAttribute("data-sidebar-preview");
    }
    return () => root.removeAttribute("data-sidebar-preview");
  }, [showFullPreview, viewMode]);

  // Drag resize handler — indicator line during drag, resize on mouseup only
  const panelRef = useRef<HTMLDivElement>(null);
  const indicatorRef = useRef<HTMLDivElement>(null);
  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    isResizing.current = true;
    const startX = e.clientX;
    const root = document.documentElement;
    const startWidth = parseInt(
      root.style.getPropertyValue("--sidebar-preview-width") ||
        String(sidebarWidthRef.current),
      10,
    );
    const indicator = indicatorRef.current;

    // Create a raw DOM capture layer — completely outside React, highest z-index
    const capture = document.createElement("div");
    capture.style.cssText =
      "position:fixed;inset:0;z-index:999999;cursor:col-resize;";
    document.body.appendChild(capture);

    const onMove = (ev: MouseEvent) => {
      if (!isResizing.current) return;
      if (indicator) {
        indicator.style.left = `${ev.clientX}px`;
        indicator.style.display = "block";
      }
    };
    const onUp = (ev: MouseEvent) => {
      if (!isResizing.current) return;
      isResizing.current = false;
      if (indicator) indicator.style.display = "none";
      capture.remove();
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      // Apply resize
      const finalClientX = ev.clientX;
      const capturedPanel = panelRef.current;
      const delta = ((startX - finalClientX) / window.innerWidth) * 100;
      const val = Math.round(Math.min(Math.max(startWidth + delta, 25), 75));
      root.style.setProperty("--sidebar-preview-width", `${val}%`);
      sidebarWidthRef.current = val;
      if (capturedPanel) capturedPanel.style.width = `${val}%`;
      localStorage.setItem("sidebar-preview-width", String(val));
      justResized.current = true;
      setTimeout(() => {
        justResized.current = false;
      }, 100);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  let projectName = "";
  let template:
    | "react"
    | "vue"
    | "vanilla"
    | "static"
    | "angular"
    | "svelte"
    | "solid"
    | "nextjs" = "vanilla";
  let error = "";
  let fileCount = 0;
  let parsed: ProjectRevealResult | null = null;

  if (result) {
    try {
      parsed =
        typeof result === "string"
          ? (JSON.parse(result) as ProjectRevealResult)
          : (result as unknown as ProjectRevealResult);

      if (parsed.error) {
        error = parsed.message || parsed.error;
      } else {
        projectName = parsed.name || "";
        template = parsed.template || "vanilla";
        fileCount = parsed.file_count || Object.keys(parsed.files).length;
      }
    } catch {
      error = t("chat.message.toolParseError");
    }
  } else {
    projectName = (args.name as string) || "";
  }

  // v2: 从 OSS 拉取文件内容
  const v2 = parsed && isV2(parsed) ? parsed : null;
  const [loadedFiles, setLoadedFiles] = useState<Record<string, string> | null>(
    null,
  );
  const [loadingError, setLoadingError] = useState(false);
  const [binaryFiles, setBinaryFiles] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!v2) return;

    const v2Files = v2.files;
    let cancelled = false;

    async function loadFiles() {
      const textEntries: Array<[string, FileManifestEntry]> = [];
      const binMap: Record<string, string> = {};

      for (const [path, entry] of Object.entries(v2Files)) {
        if (entry.is_binary) {
          const fullUrl = getFullUrl(entry.url) || entry.url;
          binMap[path] = fullUrl;
        } else {
          textEntries.push([path, entry]);
        }
      }

      setBinaryFiles(binMap);

      try {
        const { files: rawFiles, failed } = await fetchTextFiles(textEntries);

        if (failed.length > 0) {
          console.warn(
            `[reveal_project] ${failed.length} files failed to load:`,
            failed,
          );
        }

        const resolved = rewriteProjectTextFiles(rawFiles, binMap);

        if (!cancelled) {
          setLoadedFiles(resolved);
          // 如果关键文件（如 index.html）加载失败，标记错误
          if (Object.keys(resolved).length === 0 && textEntries.length > 0) {
            setLoadingError(true);
          }
        }
      } catch {
        if (!cancelled) {
          setLoadingError(true);
        }
      }
    }

    loadFiles();
    return () => {
      cancelled = true;
    };
  }, [v2]);

  // v1: 直接使用内嵌的文件内容
  const v1Files =
    parsed && !v2 && !parsed.error
      ? (parsed.files as Record<string, string>)
      : null;

  // 最终传给 Sandpack 的文件内容
  const sandpackFiles = v2 ? loadedFiles : v1Files;

  // Auto-open sidebar preview on desktop when project files are ready
  const hasClosedPreview = useRef(false);
  useEffect(() => {
    if (
      !success ||
      !sandpackFiles ||
      showFullPreview ||
      hasClosedPreview.current
    )
      return;
    if (window.innerWidth >= 640) {
      closeCurrentToolPanel();
      setShowFullPreview(true);
    }
  }, [success, sandpackFiles, showFullPreview]);

  // Escape key to close fullscreen preview
  useEffect(() => {
    if (!showFullPreview) return;
    if (viewMode === "center") {
      toast(t("project.fullscreenHint", "按 Esc 退出全屏"), {
        duration: 2000,
        position: "top-center",
        style: { borderRadius: "10px", background: "#1c1917", color: "#fff" },
      });
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        hasClosedPreview.current = true;
        setShowFullPreview(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showFullPreview, viewMode, t]);

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

  // v2 加载中状态
  if (v2 && !loadedFiles && !loadingError) {
    return (
      <div className="my-2 sm:my-3 min-w-0">
        <div className="border border-stone-200 dark:border-stone-700 rounded-xl overflow-hidden bg-white dark:bg-stone-900">
          <PreviewHeader
            variant="card"
            icon={Code2}
            title={projectName || t("project.untitled")}
            subtitle={`${t("project.fileCount", { count: fileCount })}${
              template !== "static" ? ` · ${template}` : ""
            }`}
          />
          <div className="h-[300px] sm:h-[600px] bg-stone-900 flex items-center justify-center">
            <div className="text-stone-400 text-sm flex items-center gap-2">
              <LoadingSpinner size="sm" className="text-stone-400" />
              {t("project.loadingFiles")}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (loadingError || Object.keys(sandpackFiles || {}).length === 0) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20">
        <div className="p-2.5 rounded-lg bg-amber-100 dark:bg-amber-900/30">
          <FolderTree size={20} className="text-amber-500" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-amber-700 dark:text-amber-300 truncate">
            {projectName || t("project.empty")}
          </div>
          <div className="text-xs text-amber-500 dark:text-amber-400 truncate mt-0.5">
            {loadingError ? t("project.loadFilesFailed") : t("project.noFiles")}
          </div>
        </div>
      </div>
    );
  }

  const filesForExport = sandpackFiles || {};

  return (
    <div className="my-2 sm:my-3 min-w-0">
      {showFullPreview &&
        createPortal(
          <div
            className={`fixed inset-0 z-[300] flex flex-col ${
              viewMode === "sidebar"
                ? "bg-black/50 sm:bg-transparent sm:pointer-events-none sm:items-end sm:justify-stretch"
                : "bg-stone-900"
            }`}
            onClick={() => {
              if (!isResizing.current && !justResized.current) {
                hasClosedPreview.current = true;
                setShowFullPreview(false);
              }
            }}
          >
            {/* Resize indicator line — follows mouse, no reflow */}
            <div
              ref={indicatorRef}
              className="sm:block fixed top-0 bottom-0 z-[301] pointer-events-none"
              style={{
                display: "none",
                left: 0,
                width: "2px",
                backgroundColor: "var(--theme-primary)",
                opacity: 0.4,
              }}
            />
            <div
              ref={viewMode === "sidebar" ? panelRef : undefined}
              className={`flex flex-col bg-white dark:bg-[#1e1e1e] pointer-events-auto ${
                viewMode === "sidebar"
                  ? "h-full sm:rounded-l-2xl relative shadow-[-4px_0_24px_-4px_rgba(0,0,0,0.12)] dark:shadow-[-4px_0_24px_-4px_rgba(0,0,0,0.4)]"
                  : "overflow-hidden h-full w-full relative"
              }`}
              {...(viewMode === "sidebar" ? { "data-sidebar-panel": "" } : {})}
              style={
                viewMode === "sidebar"
                  ? { width: "100%", flexShrink: 0 }
                  : undefined
              }
              onClick={(e) => e.stopPropagation()}
            >
              {/* Fullscreen close button */}
              {viewMode === "center" && (
                <button
                  onClick={() => {
                    hasClosedPreview.current = true;
                    setShowFullPreview(false);
                  }}
                  className="absolute top-3 right-3 z-[310] flex items-center justify-center w-10 h-10 rounded-full bg-black/70 hover:bg-black/90 text-white shadow-lg transition-all duration-200"
                  title={t("common.close")}
                >
                  <X size={18} />
                </button>
              )}
              {/* Resize handle */}
              {viewMode === "sidebar" && (
                <div
                  className="hidden sm:block absolute left-0 top-0 bottom-0 -translate-x-1/2 z-10 cursor-col-resize pointer-events-auto group"
                  onMouseDown={handleResizeStart}
                >
                  <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-1 rounded-full bg-transparent group-hover:bg-[var(--theme-primary)]/50 transition-colors duration-200" />
                </div>
              )}
              {/* Sidebar header */}
              {viewMode === "sidebar" && (
                <PreviewHeader
                  icon={Code2}
                  title={projectName || t("project.untitled")}
                  subtitle={`${
                    template !== "static" ? `${template} · ` : ""
                  }${t("project.fileCount", {
                    count: Object.keys(filesForExport).length,
                  })}`}
                  actions={
                    <>
                      <button
                        onClick={() => setViewMode("center")}
                        className="hidden sm:flex items-center justify-center w-8 h-8 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-all duration-200 active:scale-95"
                        title={t("documents.centerView", "居中")}
                      >
                        <Maximize
                          size={15}
                          className="text-stone-400 dark:text-stone-500"
                        />
                      </button>
                      <button
                        onClick={() =>
                          exportProjectZip(
                            filesForExport,
                            projectName,
                            binaryFiles,
                          )
                        }
                        className="flex items-center justify-center w-8 h-8 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-all duration-200 active:scale-95"
                        title={t("project.exportZip")}
                      >
                        <Download
                          size={15}
                          className="text-stone-400 dark:text-stone-500"
                        />
                      </button>
                      <button
                        onClick={() => {
                          hasClosedPreview.current = true;
                          setShowFullPreview(false);
                          setViewMode("center");
                        }}
                        className="flex items-center justify-center w-8 h-8 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-all duration-200 active:scale-95"
                        title={t("common.close")}
                      >
                        <X
                          size={16}
                          className="text-stone-500 dark:text-stone-400"
                        />
                      </button>
                    </>
                  }
                />
              )}
              <ProjectPreview
                name={projectName}
                template={template}
                files={filesForExport}
                entry={parsed?.entry}
                isFullscreen={viewMode !== "sidebar"}
                showHeader={false}
                onToggleSidebar={
                  viewMode === "center"
                    ? () => setViewMode("sidebar")
                    : undefined
                }
              />
            </div>
          </div>,
          document.body,
        )}

      <div className="border border-stone-200 dark:border-stone-700 rounded-xl overflow-hidden bg-white dark:bg-stone-900">
        <PreviewHeader
          variant="card"
          icon={Code2}
          title={projectName || t("project.untitled")}
          subtitle={`${t("project.fileCount", { count: fileCount })}${
            template !== "static" ? ` · ${template}` : ""
          }`}
          actions={
            <>
              <button
                onClick={() =>
                  exportProjectZip(filesForExport, projectName, binaryFiles)
                }
                className="flex items-center gap-1 px-1.5 sm:px-2 py-1 rounded-md text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-800 text-xs font-medium transition-colors"
              >
                <Download size={14} />
                <span className="hidden sm:inline">
                  {t("project.exportZip")}
                </span>
              </button>
              <button
                onClick={() => {
                  closeCurrentToolPanel();
                  setShowFullPreview(true);
                  setViewMode("center");
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

        <div className="h-[300px] sm:h-[600px] bg-stone-900">
          {success && Object.keys(filesForExport).length > 0 && (
            <ProjectPreview
              name={projectName}
              template={template}
              files={filesForExport}
              entry={parsed?.entry}
              showHeader={false}
              showTabs={true}
            />
          )}
        </div>
      </div>
    </div>
  );
}
