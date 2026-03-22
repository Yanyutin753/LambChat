import { ChevronDown, ChevronUp, ExternalLink, FileText } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ImageViewer } from "../../../common/ImageViewer";
import { MarkdownContent } from "../MarkdownContent";
import type { McpContentBlock, McpMultiModalResult } from "./toolUtils";
import { isMarkdownText, extractText } from "./toolUtils";

// LangChain content blocks 数组: [{"type": "text", "text": "..."}, ...]
function isContentBlocksArray(result: unknown): result is McpContentBlock[] {
  return (
    Array.isArray(result) &&
    result.length > 0 &&
    typeof result[0] === "object" &&
    result[0] !== null &&
    "type" in result[0]
  );
}

// 单个 MCP content block 的预览
export function McpBlockPreview({ block }: { block: McpContentBlock }) {
  const { t } = useTranslation();
  const [viewerOpen, setViewerOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);

  if (block.type === "image") {
    const src = block.base64
      ? `data:${block.mime_type || "image/png"};base64,${block.base64}`
      : block.url || "";
    return (
      <>
        {!loaded && (
          <div className="w-48 h-32 rounded-md border border-stone-200 dark:border-stone-700 bg-stone-100 dark:bg-stone-800 animate-pulse" />
        )}
        <img
          src={src}
          alt={t("chat.message.toolOutput")}
          className={`max-w-full max-h-48 rounded-md border border-stone-200 dark:border-stone-700 cursor-pointer hover:opacity-80 transition-opacity${
            !loaded ? " hidden" : ""
          }`}
          onClick={() => src && setViewerOpen(true)}
          onLoad={() => setLoaded(true)}
        />
        <ImageViewer
          src={src}
          alt={t("chat.message.toolOutput")}
          isOpen={viewerOpen}
          onClose={() => setViewerOpen(false)}
        />
      </>
    );
  }

  if (block.type === "file") {
    const url = block.url || "";
    const fileName = url.split("/").pop() || t("chat.message.toolFile");
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

  if (block.text) {
    return (
      <pre className="text-xs text-stone-600 dark:text-stone-300 whitespace-pre-wrap break-words max-h-32 overflow-y-auto min-w-0">
        {block.text}
      </pre>
    );
  }

  return null;
}

// 工具结果渲染组件 — 支持 str / dict / MCP 多模态
export function ToolResultContent({
  result,
}: {
  result?: string | Record<string, unknown>;
}) {
  const textContent = extractText(result);

  // LangChain content blocks 数组: [{"type": "text", "text": "..."}, ...]
  if (isContentBlocksArray(result)) {
    const blocks = result as McpContentBlock[];
    const textParts: string[] = [];
    const mediaBlocks: McpContentBlock[] = [];

    for (const block of blocks) {
      if (block.type === "text" && block.text) {
        textParts.push(block.text);
      } else if (block.type === "image" || block.type === "file") {
        mediaBlocks.push(block);
      }
    }

    const combinedText = textParts.join("\n");
    return (
      <div className="space-y-1.5">
        {combinedText && (
          <div className="text-xs text-stone-600 dark:text-stone-300 max-h-64 overflow-y-auto">
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

  if (
    typeof result === "object" &&
    result !== null &&
    "blocks" in result &&
    Array.isArray((result as McpMultiModalResult).blocks)
  ) {
    const mcp = result as McpMultiModalResult;
    return (
      <div className="space-y-1.5">
        {mcp.text &&
          (isMarkdownText(mcp.text) ? (
            <div className="text-xs text-stone-600 dark:text-stone-300 max-h-64 overflow-y-auto">
              <MarkdownContent content={mcp.text} />
            </div>
          ) : (
            <pre className="text-xs text-stone-600 dark:text-stone-300 whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
              {mcp.text}
            </pre>
          ))}
        <div className="flex flex-wrap gap-2">
          {(mcp.blocks || []).map((block, i) => (
            <McpBlockPreview key={i} block={block} />
          ))}
        </div>
      </div>
    );
  }

  // 富文本结果：dict 含 title/url/content 结构
  if (
    typeof result === "object" &&
    result !== null &&
    typeof result.content === "string" &&
    (typeof result.title === "string" || typeof result.url === "string")
  ) {
    const title = typeof result.title === "string" ? result.title : "";
    const url = typeof result.url === "string" ? result.url : "";
    return (
      <div className="rounded-md border border-stone-200 dark:border-stone-700 overflow-hidden">
        {(title || url) && (
          <div className="flex items-center gap-2 px-3 py-2 bg-stone-100 dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700">
            <FileText
              size={14}
              className="shrink-0 text-stone-500 dark:text-stone-400"
            />
            {url ? (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-medium text-stone-700 dark:text-stone-200 hover:underline truncate"
              >
                {title || url}
              </a>
            ) : (
              <span className="text-xs font-medium text-stone-700 dark:text-stone-200 truncate">
                {title}
              </span>
            )}
            {url && (
              <ExternalLink
                size={12}
                className="shrink-0 text-stone-400 dark:text-stone-500 ml-auto"
              />
            )}
          </div>
        )}
        <div className="p-3 text-xs text-stone-600 dark:text-stone-300 max-h-96 overflow-y-auto">
          <MarkdownContent content={result.content} />
        </div>
      </div>
    );
  }

  if (textContent) {
    return isMarkdownText(textContent) ? (
      <div className="text-xs text-stone-600 dark:text-stone-300 max-h-64 overflow-y-auto">
        <MarkdownContent content={textContent} />
      </div>
    ) : (
      <pre className="text-xs text-stone-600 dark:text-stone-300 max-h-32 overflow-y-auto whitespace-pre-wrap break-words">
        {textContent}
      </pre>
    );
  }

  return <JsonFallback data={result} />;
}

const MAX_JSON_COLLAPSED = 640;

function JsonFallback({ data }: { data: unknown }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const str = JSON.stringify(data, null, 2);
  const needsTruncation = str.length > MAX_JSON_COLLAPSED;
  const display =
    needsTruncation && !expanded
      ? str.slice(0, MAX_JSON_COLLAPSED) + "\n…"
      : str;

  return (
    <div>
      <pre className="text-xs text-stone-600 dark:text-stone-300 max-h-32 overflow-y-auto whitespace-pre-wrap break-words min-w-0">
        {display}
      </pre>
      {needsTruncation && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 mt-1 text-xs text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 transition-colors"
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {expanded ? t("chat.message.collapse") : t("chat.message.expandAll")}
        </button>
      )}
      {expanded && str.length > MAX_JSON_COLLAPSED && (
        <div className="mt-1 max-h-64 overflow-y-auto">
          <pre className="text-xs text-stone-600 dark:text-stone-300 whitespace-pre-wrap break-words min-w-0">
            {str}
          </pre>
        </div>
      )}
    </div>
  );
}
