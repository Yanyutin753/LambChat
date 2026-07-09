import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  File,
  Ban,
} from "lucide-react";
import { useState, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { createPortal } from "react-dom";
import { MarkdownContent } from "../MarkdownContent";
import { CopyButton, ImageViewer } from "../../../common";
import { ImageWithSkeleton } from "../ImageWithSkeleton";
import { dispatchPersonaPresetsChanged } from "../../../../hooks/personaPresetEvents";
import { getPersonaPresetMutationDetail } from "./personaPresetToolResult";
import type { McpContentBlock, McpMultiModalResult } from "./toolUtils";
import { isMarkdownText, extractText } from "./toolUtils";
import { ToolResultPanel } from "./ToolResultPanel";
import {
  extractGeneratedImageResults,
  type GeneratedImageResult,
} from "./toolImageResults";
import {
  closeBlockPreview,
  getBlockPreview,
  openBlockPreview,
  subscribeBlockPreview,
} from "./blockPreviewStore";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";

function useBlockPreview() {
  const [, setCount] = useState(0);
  useEffect(() => {
    const fn = () => setCount((c) => c + 1);
    return subscribeBlockPreview(fn);
  }, []);
  return { preview: getBlockPreview(), close: closeBlockPreview };
}

/** Standalone portal — render once at app level, survives any component tree changes */
export function BlockPreviewPortal() {
  const { t } = useTranslation();
  const { preview, close } = useBlockPreview();

  if (!preview) return null;

  let icon: React.ReactNode;
  let title: string;
  let content: React.ReactNode;

  if (preview.type === "image" && preview.src) {
    icon = <ImageIcon size={16} />;
    title = t("chat.message.toolOutput");
    content = (
      <div className="flex items-center justify-center p-4 bg-theme-bg min-h-[200px]">
        <ImageWithSkeleton
          src={preview.src}
          alt={t("chat.message.toolOutput")}
          skipUrlResolve
          className="max-w-full max-h-[70dvh] object-contain rounded-lg"
          wrapperClassName="!my-0"
        />
      </div>
    );
  } else if (preview.type === "file" && preview.url) {
    icon = <File size={16} />;
    title = preview.fileName || t("chat.message.toolFile");
    content = (
      <div className="p-4 sm:p-5 space-y-3">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-theme-bg-subtle text-sm text-theme-text-tertiary font-mono truncate">
          <span className="truncate">{preview.url}</span>
        </div>
        <a
          href={preview.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-theme-bg-subtle text-sm text-theme-text-secondary hover:bg-theme-bg-elevated transition-colors border border-theme-border"
        >
          <ExternalLink size={14} />
          {t("chat.message.toolOpenFile", "Open file")}
        </a>
      </div>
    );
  } else if (preview.type === "text" && preview.text) {
    icon = <FileText size={16} />;
    title = t("chat.message.toolOutput");
    content = (
      <div className="p-4 sm:p-5">
        <div className="flex justify-end mb-2">
          <CopyButton text={preview.text} />
        </div>
        <pre className="text-sm text-theme-text-secondary whitespace-pre-wrap break-words font-mono">
          {preview.text}
        </pre>
      </div>
    );
  } else {
    return null;
  }

  return createPortal(
    <ToolResultPanel
      open
      onClose={close}
      title={title}
      icon={icon}
      status="success"
    >
      {content}
    </ToolResultPanel>,
    document.body,
  );
}

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

  if (block.type === "image") {
    const src = block.base64
      ? `data:${block.mime_type || "image/png"};base64,${block.base64}`
      : block.url || "";
    return (
      <ImageWithSkeleton
        src={src}
        alt={t("chat.message.toolOutput")}
        skipUrlResolve
        inline
        className="max-w-full max-h-48 rounded-md border border-theme-border cursor-pointer hover:opacity-80 transition-opacity"
        onClick={() => {
          if (src) openBlockPreview({ type: "image", src });
        }}
      />
    );
  }

  if (block.type === "file") {
    const url = block.url || "";
    const fileName = url.split("/").pop() || t("chat.message.toolFile");
    return (
      <button
        onClick={() => openBlockPreview({ type: "file", url, fileName })}
        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-theme-bg-subtle text-xs text-theme-text-secondary hover:bg-theme-bg-elevated transition-colors border border-theme-border cursor-pointer"
      >
        <File size={12} />
        {fileName}
      </button>
    );
  }

  if (block.text) {
    return (
      <div className="group/pre relative">
        <pre
          onClick={() => openBlockPreview({ type: "text", text: block.text })}
          className="text-xs text-theme-text-secondary whitespace-pre-wrap break-words overflow-y-auto min-w-0 cursor-pointer hover:text-theme-text transition-colors"
        >
          {block.text}
        </pre>
        <div className="absolute top-0.5 right-0.5 opacity-0 group-hover/pre:opacity-100 transition-opacity">
          <CopyButton text={block.text} size={12} />
        </div>
      </div>
    );
  }

  return null;
}

function GeneratedImageResults({ images }: { images: GeneratedImageResult[] }) {
  const { t } = useTranslation();
  const [activeImage, setActiveImage] = useState<GeneratedImageResult | null>(
    null,
  );
  const activeImageIndex = activeImage
    ? images.findIndex((image) => image.url === activeImage.url)
    : -1;
  const previousImage =
    activeImageIndex > 0 ? images[activeImageIndex - 1] : null;
  const nextImage =
    activeImageIndex >= 0 && activeImageIndex < images.length - 1
      ? images[activeImageIndex + 1]
      : null;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3">
        {images.map((image) => (
          <figure
            key={image.url}
            className="overflow-hidden rounded-md border border-theme-border bg-theme-bg"
          >
            <button
              type="button"
              className="block w-full bg-theme-bg-elevated"
              onClick={() => setActiveImage(image)}
              aria-label={t("chat.message.openImage", "Open image")}
            >
              <ImageWithSkeleton
                src={image.url}
                alt={image.name}
                skipUrlResolve
                className="mx-auto max-h-[70dvh] w-full object-contain"
                loading="eager"
                wrapperClassName="!my-0 !shadow-none"
              />
            </button>
            <figcaption className="flex items-center gap-2 border-t border-theme-border px-3 py-2 text-xs text-theme-text-secondary">
              <ImageIcon
                size={14}
                className="shrink-0 text-theme-text-tertiary"
              />
              <span className="min-w-0 flex-1 truncate">{image.name}</span>
              <a
                href={image.url}
                target="_blank"
                rel="noopener noreferrer"
                className="shrink-0 rounded-md p-1 text-theme-text-tertiary transition-colors hover:bg-theme-bg-subtle hover:text-theme-text"
                aria-label={t("chat.message.openImage", "Open image")}
              >
                <ExternalLink size={14} />
              </a>
            </figcaption>
          </figure>
        ))}
      </div>
      {activeImage && (
        <ImageViewer
          isOpen
          src={activeImage.url}
          alt={activeImage.name}
          onClose={() => setActiveImage(null)}
          onPrevious={() => previousImage && setActiveImage(previousImage)}
          onNext={() => nextImage && setActiveImage(nextImage)}
          hasPrevious={!!previousImage}
          hasNext={!!nextImage}
          positionLabel={
            activeImageIndex >= 0
              ? `${activeImageIndex + 1} / ${images.length}`
              : undefined
          }
        />
      )}
    </div>
  );
}

// 工具结果渲染组件 — 支持 str / dict / MCP 多模态
export function ToolResultContent({
  result,
  hideCopyButton,
}: {
  result?: string | Record<string, unknown>;
  hideCopyButton?: boolean;
}) {
  const personaMutationDetail = useMemo(
    () => getPersonaPresetMutationDetail(result),
    [result],
  );
  const lastPersonaMutationKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!personaMutationDetail) return;
    const key = JSON.stringify(personaMutationDetail);
    if (lastPersonaMutationKeyRef.current === key) return;
    lastPersonaMutationKeyRef.current = key;
    dispatchPersonaPresetsChanged(personaMutationDetail);
  }, [personaMutationDetail]);

  const textContent = extractText(result);
  const generatedImages = useMemo(() => {
    const directImages = extractGeneratedImageResults(result);
    if (directImages.length > 0) return directImages;

    if (typeof result !== "string") return [];
    try {
      return extractGeneratedImageResults(JSON.parse(result));
    } catch {
      return [];
    }
  }, [result]);

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
          <div className="group/result relative text-xs text-theme-text-secondary overflow-y-auto">
            {isMarkdownText(combinedText) ? (
              <MarkdownContent content={combinedText} />
            ) : (
              combinedText
            )}
            <ToolHoverCopyButton
              text={combinedText}
              position="resultCompact"
              hidden={hideCopyButton}
            />
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
            <div className="group/result relative text-xs text-theme-text-secondary overflow-y-auto">
              <MarkdownContent content={mcp.text} />
              <ToolHoverCopyButton
                text={mcp.text}
                position="resultCompact"
                hidden={hideCopyButton}
              />
            </div>
          ) : (
            <pre className="group/result relative text-xs text-theme-text-secondary whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
              {mcp.text}
              <ToolHoverCopyButton
                text={mcp.text}
                position="resultCompact"
                hidden={hideCopyButton}
              />
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

  if (generatedImages.length > 0) {
    return <GeneratedImageResults images={generatedImages} />;
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
      <div className="rounded-md border border-theme-border overflow-hidden">
        {(title || url) && (
          <div className="flex items-center gap-2 px-3 py-2 bg-theme-bg-subtle border-b border-theme-border">
            <FileText size={14} className="shrink-0 text-theme-text-tertiary" />
            {url ? (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-medium text-theme-text hover:underline truncate"
              >
                {title || url}
              </a>
            ) : (
              <span className="text-xs font-medium text-theme-text truncate">
                {title}
              </span>
            )}
            {url && (
              <ExternalLink
                size={12}
                className="shrink-0 text-theme-text-tertiary ml-auto"
              />
            )}
          </div>
        )}
        <div className="group/rich relative p-3 text-xs text-theme-text-secondary max-h-96 overflow-y-auto">
          <MarkdownContent content={result.content} />
          <div className="absolute top-1 right-1 opacity-0 group-hover/rich:opacity-100 transition-opacity">
            {!hideCopyButton && <CopyButton text={result.content} size={12} />}
          </div>
        </div>
      </div>
    );
  }

  // Approval / tool rejection response — show human-friendly summary instead of raw JSON
  if (
    typeof result === "object" &&
    result !== null &&
    (result as Record<string, unknown>).success === false &&
    typeof (result as Record<string, unknown>).reason === "string"
  ) {
    return <RejectionResult data={result as Record<string, unknown>} />;
  }

  // Plain object or JSON-parseable string — render as JSON
  if (typeof result === "object" && result !== null) {
    return <JsonFallback data={result} hideCopyButton={hideCopyButton} />;
  }

  if (textContent && typeof result === "string") {
    try {
      const parsed = JSON.parse(textContent);
      if (typeof parsed === "object" && parsed !== null) {
        return <JsonFallback data={parsed} hideCopyButton={hideCopyButton} />;
      }
    } catch {
      // not JSON, fall through
    }
  }

  if (textContent) {
    return isMarkdownText(textContent) ? (
      <div className="group/result relative text-xs text-theme-text-secondary overflow-y-auto">
        <MarkdownContent content={textContent} />
        <ToolHoverCopyButton
          text={textContent}
          position="resultCompact"
          hidden={hideCopyButton}
        />
      </div>
    ) : (
      <pre className="group/result relative text-xs text-theme-text-secondary overflow-y-auto whitespace-pre-wrap break-words">
        {textContent}
        <ToolHoverCopyButton
          text={textContent}
          position="resultCompact"
          hidden={hideCopyButton}
        />
      </pre>
    );
  }

  return <JsonFallback data={result} hideCopyButton={hideCopyButton} />;
}

const MAX_JSON_COLLAPSED = 640;

function JsonFallback({
  data,
  hideCopyButton,
}: {
  data: unknown;
  hideCopyButton?: boolean;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const str = JSON.stringify(data, null, 2);
  const needsTruncation = str.length > MAX_JSON_COLLAPSED;
  const display =
    needsTruncation && !expanded
      ? str.slice(0, MAX_JSON_COLLAPSED) + "\n…"
      : str;

  return (
    <div className="group/json relative">
      <div className="absolute top-1 right-1 opacity-0 group-hover/json:opacity-100 transition-opacity z-10">
        {!hideCopyButton && <CopyButton text={str} size={12} />}
      </div>
      <pre className="text-xs text-theme-text-secondary overflow-y-auto whitespace-pre-wrap break-words min-w-0">
        {display}
      </pre>
      {needsTruncation && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 mt-1 text-xs text-theme-text-tertiary hover:text-theme-text transition-colors"
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {expanded ? t("chat.message.collapse") : t("chat.message.expandAll")}
        </button>
      )}
    </div>
  );
}

/**
 * Human-friendly renderer for approval / tool rejection responses.
 * Matches objects like:
 *   { success: false, action: "not_created", reason: "rejected", message: "...", preview: {...} }
 */
function RejectionResult({ data }: { data: Record<string, unknown> }) {
  const { t } = useTranslation();
  const [showDetails, setShowDetails] = useState(false);

  const message =
    (typeof data.message === "string" && data.message) || undefined;
  const preview = data.preview as Record<string, unknown> | undefined;
  const taskName =
    preview && typeof preview.name === "string" ? preview.name : undefined;
  const description =
    preview && typeof preview.description === "string"
      ? preview.description
      : undefined;
  const schedule =
    preview && typeof preview.schedule === "string"
      ? preview.schedule
      : undefined;

  // Summary line for the card
  const summary = message || t("chat.message.rejected");

  return (
    <div className="space-y-1.5">
      <div className="flex items-start gap-2 rounded-xl border border-[color-mix(in_srgb,var(--theme-primary)_14%,var(--theme-border))] bg-theme-bg-card px-3 py-2.5 shadow-[0_12px_28px_-24px_color-mix(in_srgb,var(--theme-primary)_45%,transparent)]">
        <Ban size={14} className="shrink-0 mt-0.5 text-theme-text-tertiary" />
        <div className="min-w-0 flex-1 space-y-1">
          {/* Task name (if available) */}
          {taskName && (
            <p
              className="text-sm font-medium truncate"
              style={{ color: "var(--theme-text)" }}
            >
              {taskName}
            </p>
          )}

          {/* Summary / reason */}
          <p
            className="text-xs"
            style={{ color: "var(--theme-text-secondary)" }}
          >
            {summary}
          </p>

          {/* Schedule info (compact, one line) */}
          {schedule && (
            <p
              className="text-[11px] font-mono truncate"
              style={{ color: "var(--theme-text-tertiary)" }}
            >
              {schedule}
            </p>
          )}

          {/* Description (truncated) */}
          {description && !showDetails && (
            <p
              className="text-[11px] line-clamp-2"
              style={{ color: "var(--theme-text-tertiary)" }}
            >
              {description}
            </p>
          )}

          {/* Expanded details */}
          {showDetails && (
            <div className="space-y-2 pt-2 border-t border-theme-border">
              {description && (
                <div>
                  <p
                    className="text-[10px] font-medium uppercase tracking-wider mb-0.5"
                    style={{ color: "var(--theme-text-tertiary)" }}
                  >
                    {t("chat.message.description")}
                  </p>
                  <p
                    className="text-xs whitespace-pre-wrap break-words"
                    style={{ color: "var(--theme-text-secondary)" }}
                  >
                    {description}
                  </p>
                </div>
              )}
              {preview && (
                <div>
                  <p
                    className="text-[10px] font-medium uppercase tracking-wider mb-0.5"
                    style={{ color: "var(--theme-text-tertiary)" }}
                  >
                    {t("chat.message.details")}
                  </p>
                  <pre className="text-[11px] text-theme-text-tertiary overflow-y-auto whitespace-pre-wrap break-words max-h-48 min-w-0 rounded-lg border border-theme-border bg-theme-bg p-2.5">
                    {JSON.stringify(preview, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}

          {/* Expand/collapse toggle */}
          {(description || preview) && (
            <button
              onClick={() => setShowDetails((v) => !v)}
              className="flex items-center gap-0.5 text-[11px] transition-colors hover:text-theme-text-secondary"
              style={{ color: "var(--theme-text-tertiary)" }}
            >
              {showDetails ? (
                <ChevronUp size={11} />
              ) : (
                <ChevronDown size={11} />
              )}
              {showDetails
                ? t("chat.message.collapse")
                : t("chat.message.expandAll")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
