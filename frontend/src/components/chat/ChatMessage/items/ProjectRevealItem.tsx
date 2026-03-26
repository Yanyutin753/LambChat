import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { ExternalLink, Code2, FolderTree, Download } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../../common";
import ProjectPreview from "../../../documents/previews/ProjectPreview";
import { exportProjectZip } from "../../../../utils/exportProjectZip";
import { getFullUrl } from "../../../../services/api/config";
import { rewriteProjectTextFiles } from "./projectRevealAssetUtils";

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
            console.warn(`[reveal_project] Failed to fetch ${path}: ${resp.status}`);
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
          <div className="flex items-center justify-between px-2 sm:px-4 py-2 sm:py-3 bg-stone-50 dark:bg-stone-800/50 border-b border-stone-200 dark:border-stone-700 gap-2">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
              <div className="p-1.5 sm:p-2 rounded-lg bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-400 shrink-0">
                <Code2 size={16} />
              </div>
              <div className="min-w-0">
                <h4 className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate max-w-[100px] sm:max-w-none">
                  {projectName || t("project.untitled")}
                </h4>
                <p className="text-xs text-stone-500 dark:text-stone-400 hidden sm:block">
                  {t("project.fileCount", { count: fileCount })}
                  {template !== "static" && ` · ${template}`}
                </p>
              </div>
            </div>
          </div>
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
            className="fixed inset-0 z-[300] flex items-center justify-center bg-black/70 p-2 sm:p-4"
            onClick={() => setShowFullPreview(false)}
          >
            <div
              className="w-full h-full sm:h-[90vh] sm:max-w-6xl bg-white dark:bg-stone-900 rounded-none sm:rounded-2xl overflow-hidden shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <ProjectPreview
                name={projectName}
                template={template}
                files={filesForExport}
                entry={parsed?.entry}
                onClose={() => setShowFullPreview(false)}
                isFullscreen
              />
            </div>
          </div>,
          document.body,
        )}

      <div className="border border-stone-200 dark:border-stone-700 rounded-xl overflow-hidden bg-white dark:bg-stone-900">
        <div className="flex items-center justify-between px-2 sm:px-4 py-2 sm:py-3 bg-stone-50 dark:bg-stone-800/50 border-b border-stone-200 dark:border-stone-700 gap-2">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
            <div className="p-1.5 sm:p-2 rounded-lg bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-400 shrink-0">
              <Code2 size={16} />
            </div>
            <div className="min-w-0">
              <h4 className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate max-w-[100px] sm:max-w-none">
                {projectName || t("project.untitled")}
              </h4>
              <p className="text-xs text-stone-500 dark:text-stone-400 hidden sm:block">
                {t("project.fileCount", { count: fileCount })}
                {template !== "static" && ` · ${template}`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() =>
                exportProjectZip(filesForExport, projectName, binaryFiles)
              }
              className="flex items-center gap-1 px-1.5 sm:px-2 py-1 rounded-md text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-800 text-xs font-medium transition-colors"
            >
              <Download size={14} />
              <span className="hidden sm:inline">{t("project.exportZip")}</span>
            </button>
            <button
              onClick={() => setShowFullPreview(true)}
              className="flex items-center gap-1 px-1.5 sm:px-2 py-1 rounded-md text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-800 text-xs font-medium transition-colors"
            >
              <ExternalLink size={14} />
              <span className="hidden sm:inline">{t("project.expand")}</span>
            </button>
          </div>
        </div>

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
