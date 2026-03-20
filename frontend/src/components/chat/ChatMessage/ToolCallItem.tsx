import { memo, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { clsx } from "clsx";
import { Wrench, ExternalLink, Code2, FolderTree, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner, CollapsiblePill, ImageViewer } from "../../common";
import type { CollapsibleStatus } from "../../common";
import DocumentPreview from "../../documents/DocumentPreview";
import { getFileTypeInfo } from "../../documents/utils";
import { getFullUrl } from "../../../services/api";
import ProjectPreview from "../../documents/previews/ProjectPreview";
import { MarkdownContent } from "./MarkdownContent";

// 检测文本是否可能是 markdown 格式
function isMarkdownText(text: string): boolean {
  // 检查常见的 markdown 语法
  const markdownPatterns = [
    /^#{1,6}\s/m, // 标题 (# ## ###)
    /^\*\s/m, // 无序列表 (* )
    /^-{1,3}\s/m, // 无序列表 (- -- ---)
    /^\d+\.\s/m, // 有序列表 (1. 2. )
    /\[.+\]\(.+\)/, // 链接 [text](url)
    /\*\*.+\*\*/, // 粗体 **text**
    /\*.+\*/, // 斜体 *text*
    /`[^`]+`/, // 行内代码 `code`
    /^```[\s\S]*?^```/m, // 代码块
    /^\s*>/m, // 引用 >
    /\|.+\|/, // 表格
  ];

  // 至少匹配 2 种 markdown 模式才认为是 markdown
  let matchCount = 0;
  for (const pattern of markdownPatterns) {
    if (pattern.test(text)) {
      matchCount++;
      if (matchCount >= 2) return true;
    }
  }
  return false;
}

// MCP content block 类型 (后端 _normalize_content 返回)
interface McpContentBlock {
  type: "text" | "image" | "file";
  text?: string;
  base64?: string;
  url?: string;
  mime_type?: string;
}

// MCP 多模态结果格式
interface McpMultiModalResult {
  text?: string;
  blocks?: McpContentBlock[];
}

// 去除 cat -n 格式的行号前缀 (如 "  201\tcontent" 或 "201→content")
function stripLineNumbers(text: string): string {
  return text.replace(/^\s*\d+[→\t]/gm, "");
}

// Read File 工具专用渲染 — 去行号 + 文件路径 header + 代码块样式
const ReadFileItem = memo(function ReadFileItem({
  args,
  result,
  success,
  isPending,
}: {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
}) {
  const filePath = (args.file_path as string) || "";
  const fileName = filePath.split("/").pop() || filePath;
  const offset = args.offset as number | undefined;
  const limit = args.limit as number | undefined;

  // useMemo 缓存行号去除，避免大文件重复计算
  const displayContent = useMemo(() => {
    if (!result) return "";
    const raw = typeof result === "string" ? result : JSON.stringify(result, null, 2);
    return stripLineNumbers(raw);
  }, [result]);

  return (
    <CollapsiblePill
      status={isPending ? "loading" : success ? "success" : "error"}
      icon={<FileText size={12} className="shrink-0 opacity-50" />}
      label={fileName || "Read"}
      variant="tool"
      expandable={!!displayContent}
    >
      {displayContent && (
        <div className="mt-2 ml-4 pl-3 border-l-2 border-stone-200/60 dark:border-stone-700/50">
          {/* 文件路径 header */}
          <div className="flex items-center gap-2 mb-2 px-2 py-1.5 rounded-md bg-stone-100 dark:bg-stone-800 text-xs text-stone-500 dark:text-stone-400 font-mono">
            <span className="truncate">{filePath}</span>
            {(offset !== undefined || limit !== undefined) && (
              <span className="shrink-0 text-stone-400 dark:text-stone-500">
                :L{offset ?? 1}{limit ? `-${(offset ?? 1) + limit}` : ""}
              </span>
            )}
          </div>
          {/* 代码内容 */}
          <pre
            className={clsx(
              "text-xs max-h-64 overflow-y-auto rounded-md p-3",
              "bg-stone-50 dark:bg-stone-900 border border-stone-200/60 dark:border-stone-700/50",
              "text-stone-700 dark:text-stone-300 whitespace-pre-wrap break-words font-mono",
            )}
          >
            {displayContent}
          </pre>
        </div>
      )}
    </CollapsiblePill>
  );
});

// 工具结果渲染组件 — 支持 str / dict / MCP 多模态
function ToolResultContent({
  result,
}: {
  result?: string | Record<string, unknown>;
}) {
  // LangChain content blocks 数组: [{"type": "text", "text": "..."}, ...]
  if (Array.isArray(result)) {
    const blocks = result as unknown[];
    const textParts: string[] = [];
    const mediaBlocks: McpContentBlock[] = [];

    for (const block of blocks) {
      if (typeof block === "object" && block !== null) {
        const b = block as Record<string, unknown>;
        if (b.type === "text" && typeof b.text === "string") {
          textParts.push(b.text);
        } else if (b.type === "image" || b.type === "file") {
          mediaBlocks.push(b as unknown as McpContentBlock);
        } else if (typeof b.text === "string") {
          textParts.push(b.text);
        }
      } else if (typeof block === "string") {
        textParts.push(block);
      }
    }

    const combinedText = textParts.join("\n");
    return (
      <div className="space-y-1.5">
        {combinedText && (
          <div className="text-xs text-stone-600 dark:text-stone-300 max-h-32 overflow-y-auto">
            {isMarkdownText(combinedText) ? (
              <MarkdownContent content={combinedText} />
            ) : (
              combinedText
            )}
          </div>
        )}
        {mediaBlocks.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {mediaBlocks.map((block, i) => (
              <McpBlockPreview key={i} block={block} />
            ))}
          </div>
        )}
      </div>
    );
  }

  // MCP 多模态格式: {"text": "...", "blocks": [...]}
  if (
    typeof result === "object" &&
    result !== null &&
    "blocks" in result &&
    Array.isArray((result as McpMultiModalResult).blocks)
  ) {
    const mcp = result as McpMultiModalResult;
    return (
      <div className="space-y-1.5">
        {mcp.text && (
          <pre className="text-xs text-stone-600 dark:text-stone-300 whitespace-pre-wrap break-words">
            {isMarkdownText(mcp.text) ? (
              <MarkdownContent content={mcp.text} />
            ) : (
              mcp.text
            )}
          </pre>
        )}
        <div className="flex flex-wrap gap-2">
          {(mcp.blocks || []).map((block, i) => (
            <McpBlockPreview key={i} block={block} />
          ))}
        </div>
      </div>
    );
  }

  // 普通字符串
  if (typeof result === "string") {
    return isMarkdownText(result) ? (
      <div className="text-xs text-stone-600 dark:text-stone-300 max-h-32 overflow-y-auto">
        <MarkdownContent content={result} />
      </div>
    ) : (
      <pre className="text-xs text-stone-600 dark:text-stone-300 max-h-32 overflow-y-auto whitespace-pre-wrap break-words">
        {result}
      </pre>
    );
  }

  // 普通 dict / JSON
  return (
    <pre className="text-xs text-stone-600 dark:text-stone-300 max-h-32 overflow-y-auto whitespace-pre-wrap break-words">
      {JSON.stringify(result, null, 2)}
    </pre>
  );
}

// 单个 MCP content block 的预览
function McpBlockPreview({ block }: { block: McpContentBlock }) {
  if (block.type === "image") {
    const src = block.base64
      ? `data:${block.mime_type || "image/png"};base64,${block.base64}`
      : block.url || "";
    return (
      <img
        src={src}
        alt="tool output"
        className="max-w-full max-h-48 rounded-md border border-stone-200 dark:border-stone-700 cursor-pointer hover:opacity-80 transition-opacity"
        onClick={() => src && window.open(src, "_blank")}
      />
    );
  }

  if (block.type === "file") {
    const url = block.url || "";
    const fileName = url.split("/").pop() || "file";
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-stone-100 dark:bg-stone-800 text-xs text-stone-600 dark:text-stone-300 hover:bg-stone-200 dark:hover:bg-stone-700 transition-colors border border-stone-200 dark:border-stone-700"
      >
        <ExternalLink size={12} />
        {fileName}
      </a>
    );
  }

  // text block (fallback, normally rendered as text)
  if (block.text) {
    return (
      <pre className="text-xs text-stone-600 dark:text-stone-300 whitespace-pre-wrap break-words">
        {block.text}
      </pre>
    );
  }

  return null;
}

// Collapsible Tool Call Item (compact design)
export { ReadFileItem };

export function ToolCallItem({
  name,
  args,
  result,
  success,
  isPending,
}: {
  name: string;
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
}) {
  const { t } = useTranslation();
  const hasResult = result !== undefined;

  // 处理 partial 格式：尝试解析或显示原始字符串
  const displayArgs = (() => {
    if (args.partial !== undefined) {
      // 尝试解析 partial JSON
      try {
        return JSON.parse(args.partial as string);
      } catch {
        // 解析失败，显示原始字符串
        return { partial: args.partial };
      }
    }
    return args;
  })();

  const hasArgs = Object.keys(displayArgs).length > 0;

  // Map props to CollapsibleStatus
  let status: CollapsibleStatus = "idle";
  if (isPending) {
    status = "loading";
  } else if (success) {
    status = "success";
  } else if (hasResult) {
    status = "error";
  }

  const canExpand = hasArgs || hasResult;

  return (
    <CollapsiblePill
      status={status}
      icon={<Wrench size={12} className="shrink-0 opacity-50" />}
      label={name}
      variant="tool"
      expandable={canExpand}
    >
      {canExpand && (
        <div className="mt-2 ml-4 pl-3 border-l-2 border-stone-200/60 dark:border-stone-700/50 space-y-2">
          {/* Arguments */}
          {hasArgs && (
            <div className="p-2 rounded-md bg-stone-50/80 dark:bg-stone-800/50">
              <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-1 font-medium">
                {t("chat.message.args")}
              </div>
              <pre className="text-xs text-stone-600 dark:text-stone-300 overflow-x-auto">
                {JSON.stringify(displayArgs, null, 2)}
              </pre>
            </div>
          )}

          {/* Result */}
          {hasResult && (
            <div className="p-2 rounded-md bg-stone-50/80 dark:bg-stone-800/50">
              <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-1 font-medium">
                {t("chat.message.result")}
              </div>
              <ToolResultContent result={result} />
            </div>
          )}

          {/* Pending state */}
          {isPending && (
            <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400">
              <LoadingSpinner size="xs" />
              <span>{t("chat.message.running")}</span>
            </div>
          )}
        </div>
      )}
    </CollapsiblePill>
  );
}

// File Reveal Item - for showing reveal_file tool results
// 新格式：与 UploadResult 一致
interface FileRevealResultNew {
  key: string;
  url: string;
  name: string;
  type: "image" | "video" | "audio" | "document";
  mimeType: string;
  size: number;
  _meta?: {
    path: string;
    description?: string;
  };
}

// 旧格式：带 error 的情况
interface FileInfo {
  path: string;
  description?: string;
  s3_url?: string;
  s3_key?: string;
  size?: number;
  error?: string;
}

interface FileRevealResultOld {
  type: "file_reveal";
  file: FileInfo;
}

type FileRevealResult = FileRevealResultNew | FileRevealResultOld;

export function FileRevealItem({
  args,
  result,
  success,
  isPending,
}: {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
}) {
  const { t } = useTranslation();
  const [showPreview, setShowPreview] = useState(false);
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);

  // Parse result to get path and S3 info
  let filePath = "";
  let description = "";
  let s3Key = "";
  let s3Url = "";
  let fileSize: number | undefined = undefined;
  let error = "";

  if (result) {
    try {
      // result 可能是字符串（需要 JSON.parse）或对象（直接使用）
      let parsed: FileRevealResult;

      if (typeof result === "object") {
        // 已经是对象，直接使用
        parsed = result as unknown as FileRevealResult;
      } else {
        // 字符串，需要解析
        let jsonStr = result;
        const contentMatch = result.match(/content='(.+?)'(\s|$)/);
        if (contentMatch) {
          // Handle escaped single quotes and possible nested quotes
          jsonStr = contentMatch[1].replace(/\\'/g, "'");
        }
        parsed = JSON.parse(jsonStr);
      }

      // 检查是否为新格式（有 key 和 url 字段）
      if ("key" in parsed && "url" in parsed) {
        // 新格式：使用 getFullUrl 处理相对路径
        s3Key = parsed.key;
        s3Url = getFullUrl(parsed.url) || "";
        fileSize = parsed.size;
        // 从 _meta 获取额外信息
        if (parsed._meta) {
          filePath = parsed._meta.path;
          description = parsed._meta.description || "";
        } else {
          // 从 name 推断
          filePath = parsed.name;
        }
      } else if (parsed.type === "file_reveal" && "file" in parsed) {
        // 旧格式（错误情况）
        filePath = parsed.file.path;
        description = parsed.file.description || "";
        s3Key = parsed.file.s3_key || "";
        fileSize = parsed.file.size;
        error = parsed.file.error || "";
      }
    } catch {
      // Parse failed, use values from args
      filePath = (args.path as string) || "";
      description = (args.description as string) || "";
    }
  } else {
    filePath = (args.path as string) || "";
    description = (args.description as string) || "";
  }

  const fileName = filePath.split("/").pop() || filePath;
  const fileInfo = getFileTypeInfo(filePath);
  const FileIcon = fileInfo.icon;
  const color = fileInfo.color;
  const bg = fileInfo.bg;
  const isImage = fileInfo.category === "image";
  const isVideo = fileInfo.category === "video";
  const canPreview = isImage || isVideo;

  // Pending state
  if (isPending) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-900">
        <div className={`p-2.5 rounded-lg ${bg}`}>
          <LoadingSpinner size="sm" className={color} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-stone-700 dark:text-stone-300 truncate">
            {fileName}
          </div>
          {description && (
            <div className="text-xs text-stone-500 dark:text-stone-400 truncate mt-0.5">
              {description}
            </div>
          )}
        </div>
        <div className="text-xs text-amber-600 dark:text-amber-400">
          {t("chat.message.running")}
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20">
        <div className={`p-2.5 rounded-lg bg-red-100 dark:bg-red-900/30`}>
          <FileIcon size={20} className="text-red-500" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-red-700 dark:text-red-300 truncate">
            {fileName}
          </div>
          <div className="text-xs text-red-500 dark:text-red-400 truncate mt-0.5">
            {error}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="my-2 sm:my-3">
      {/* DocumentPreview for non-image files */}
      {showPreview && filePath && !isImage && (
        <DocumentPreview
          path={filePath}
          s3Key={s3Key || undefined}
          signedUrl={s3Url || undefined}
          fileSize={fileSize}
          onClose={() => setShowPreview(false)}
        />
      )}

      {/* ImageViewer for image files */}
      {imageViewerSrc && (
        <ImageViewer
          src={imageViewerSrc}
          isOpen={!!imageViewerSrc}
          onClose={() => setImageViewerSrc(null)}
        />
      )}

      {/* File card - ChatGPT style */}
      {canPreview && s3Url && success ? (
        <div
          className={clsx(
            "w-full rounded-xl border overflow-hidden transition-all",
            "border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-900",
            "hover:shadow-lg hover:border-stone-300 dark:hover:border-stone-600",
          )}
        >
          {/* Inline preview */}
          <div
            className="relative group cursor-pointer"
            onClick={() => isImage && setImageViewerSrc(s3Url)}
          >
            {isImage ? (
              <img
                src={s3Url}
                alt={fileName}
                className="w-full max-h-64 object-cover"
                loading="lazy"
              />
            ) : (
              <video
                src={s3Url}
                controls
                preload="metadata"
                className="w-full max-h-64 bg-black"
                playsInline
              />
            )}
            {/* Hover overlay for images */}
            {isImage && (
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center">
                <div className="opacity-0 group-hover:opacity-100 transition-opacity p-2 rounded-full bg-white/90 dark:bg-stone-800/90 shadow-lg">
                  <ExternalLink
                    size={16}
                    className="text-stone-600 dark:text-stone-300"
                  />
                </div>
              </div>
            )}
          </div>

          {/* File info bar */}
          <div
            className="flex items-center gap-2 px-3 py-2 bg-stone-50 dark:bg-stone-800/50 border-t border-stone-200 dark:border-stone-700"
            onClick={() => !isImage && setShowPreview(true)}
          >
            <div className={`p-1.5 rounded-md shrink-0 ${bg}`}>
              <FileIcon size={14} className={color} />
            </div>
            <span className="text-xs font-medium text-stone-700 dark:text-stone-300 truncate flex-1">
              {fileName}
            </span>
            {description && (
              <span className="text-xs text-stone-400 dark:text-stone-500 truncate max-w-[200px]">
                {description}
              </span>
            )}
          </div>
        </div>
      ) : (
        <button
          onClick={() => {
            if (!filePath || !success) return;
            if (isImage && s3Url) {
              setImageViewerSrc(s3Url);
            } else {
              setShowPreview(true);
            }
          }}
          className={clsx(
            "w-full flex items-center gap-3 p-4 rounded-xl border transition-all cursor-pointer text-left",
            success
              ? "border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-900 hover:shadow-lg hover:border-stone-300 dark:hover:border-stone-600 hover:scale-[1.005] transition-transform"
              : "border-stone-200 dark:border-stone-700 bg-stone-50 dark:bg-stone-800 opacity-70",
          )}
          disabled={!filePath || !success}
        >
          {/* File icon */}
          <div className={`p-2.5 rounded-lg shrink-0 ${bg}`}>
            <FileIcon size={20} className={color} />
          </div>

          {/* File info */}
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-stone-800 dark:text-stone-200 truncate">
              {fileName}
            </div>
            {description && (
              <div className="text-xs text-stone-500 dark:text-stone-400 truncate mt-1">
                {description}
              </div>
            )}
          </div>

          {/* Open icon */}
          {success && filePath && (
            <div className="shrink-0 p-2 rounded-lg bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400">
              <ExternalLink size={16} />
            </div>
          )}
        </button>
      )}
    </div>
  );
}

// Project Reveal Item - for showing reveal_project tool results
interface ProjectRevealResult {
  type: "project_reveal";
  name: string;
  description?: string;
  template: "react" | "vue" | "vanilla" | "static";
  files: Record<string, string>;
  entry?: string;
  path?: string;
  file_count?: number;
  error?: string;
  message?: string;
}

export function ProjectRevealItem({
  args,
  result,
  success,
  isPending,
}: {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
}) {
  const { t } = useTranslation();
  const [showFullPreview, setShowFullPreview] = useState(false);

  // Parse result
  let projectName = "";
  let template: "react" | "vue" | "vanilla" | "static" = "vanilla";
  let files: Record<string, string> = {};
  let entry: string | undefined;
  let fileCount = 0;
  let error = "";

  if (result) {
    try {
      // result 可能是字符串（需要 JSON.parse）或对象（直接使用）
      const parsed: ProjectRevealResult =
        typeof result === "string" ? JSON.parse(result) : result;

      if (parsed.error) {
        error = parsed.message || parsed.error;
      } else {
        projectName = parsed.name || "";
        template = parsed.template || "vanilla";
        files = parsed.files || {};
        entry = parsed.entry;
        fileCount = parsed.file_count || Object.keys(files).length;
      }
    } catch {
      error = "Failed to parse project data";
    }
  } else {
    projectName = (args.name as string) || "";
  }

  // Pending state
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
            {projectName || t("project.loading", "加载项目中...")}
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

  // Error state
  if (error) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20">
        <div className="p-2.5 rounded-lg bg-red-100 dark:bg-red-900/30">
          <Code2 size={20} className="text-red-500" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-red-700 dark:text-red-300 truncate">
            {projectName || t("project.error", "项目加载失败")}
          </div>
          <div className="text-xs text-red-500 dark:text-red-400 truncate mt-0.5">
            {error}
          </div>
        </div>
      </div>
    );
  }

  // Empty files
  if (Object.keys(files).length === 0) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20">
        <div className="p-2.5 rounded-lg bg-amber-100 dark:bg-amber-900/30">
          <FolderTree size={20} className="text-amber-500" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-amber-700 dark:text-amber-300 truncate">
            {projectName || t("project.empty", "空项目")}
          </div>
          <div className="text-xs text-amber-500 dark:text-amber-400 truncate mt-0.5">
            {t("project.noFiles", "没有找到可预览的文件")}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="my-2 sm:my-3">
      {/* Full screen preview modal */}
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
                files={files}
                entry={entry}
                onClose={() => setShowFullPreview(false)}
                isFullscreen
              />
            </div>
          </div>,
          document.body,
        )}

      {/* Compact preview card */}
      <div className="border border-stone-200 dark:border-stone-700 rounded-xl overflow-hidden bg-white dark:bg-stone-900">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-stone-50 dark:bg-stone-800/50 border-b border-stone-200 dark:border-stone-700">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-400">
              <Code2 size={16} />
            </div>
            <div>
              <h4 className="text-sm font-medium text-stone-900 dark:text-stone-100">
                {projectName || t("project.untitled", "未命名项目")}
              </h4>
              <p className="text-xs text-stone-500 dark:text-stone-400">
                {t("project.fileCount", "{{count}} 个文件", {
                  count: fileCount,
                })}
                {template !== "static" && ` · ${template}`}
              </p>
            </div>
          </div>

          <button
            onClick={() => setShowFullPreview(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-stone-200 dark:bg-stone-700 hover:bg-stone-300 dark:hover:bg-stone-600 text-stone-700 dark:text-stone-300 text-xs font-medium transition-colors"
          >
            <ExternalLink size={14} />
            <span>{t("project.expand", "展开")}</span>
          </button>
        </div>

        {/* Preview area - inline Sandpack */}
        <div className="h-[300px] sm:h-[450px] bg-stone-900">
          {success && Object.keys(files).length > 0 && (
            <ProjectPreview
              name={projectName}
              template={template}
              files={files}
              entry={entry}
              showHeader={false}
              showTabs={true}
            />
          )}
        </div>
      </div>
    </div>
  );
}
