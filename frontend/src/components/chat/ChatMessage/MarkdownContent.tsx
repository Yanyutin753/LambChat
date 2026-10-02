import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import React, { memo, useState, useId } from "react";
import { Check, Download, Table2, Code2, X, Minus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { getFullUrl } from "../../../services/api/config";
import { MermaidDiagram } from "./MermaidDiagram";
import { DeferredCodeMirrorViewer } from "../../common/DeferredCodeMirrorViewer";
import { ImageViewer } from "../../common";
import { cjkGfmRemarkPlugins } from "../../common/markdownRemarkPlugins";
import { createHeadingAnchorId } from "../../layout/AppContent/messageOutline";
import { getFileLinkInfo } from "../../documents/utils";
import { setActiveRevealPreviewState } from "./items/activeRevealPreviewStore";
import { createActiveRevealPreviewState } from "./items/revealPreviewState";
import { shouldInterceptFilePreviewLink } from "./items/revealPreviewLinks";
import { useClipboardCopy } from "../../../hooks/useClipboardCopy";
import { buildChatThumbUrl } from "../../../utils/chatThumbs";
import { useSessionImageGallery } from "./sessionImageGallery";
import { ImageWithSkeleton } from "./ImageWithSkeleton";
import { normalizeMarkdownCodeFences } from "./markdownCodeFences";
import { CopyButton } from "../../common/CopyButton";

function extractNodeText(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }

  if (Array.isArray(node)) {
    return node.map((child) => extractNodeText(child)).join("");
  }

  if (React.isValidElement<{ children?: React.ReactNode }>(node)) {
    return extractNodeText(node.props.children);
  }

  return "";
}

function renderLinkedImages(children: React.ReactNode): React.ReactNode {
  return React.Children.map(children, (child) => {
    if (
      !React.isValidElement<{
        node?: { tagName?: string };
        src?: string;
        alt?: string;
        children?: React.ReactNode;
      }>(child)
    )
      return child;
    if (child.props.node?.tagName === "img") {
      const src = getFullUrl(child.props.src);
      return (
        <ImageWithSkeleton
          key={child.key}
          src={src}
          thumbSrc={buildChatThumbUrl(src)}
          alt={child.props.alt}
          loading="eager"
          className="max-w-lg h-auto rounded-lg shadow hover:opacity-90 transition-opacity"
        />
      );
    }
    return child.props.children === undefined
      ? child
      : React.cloneElement(child, {
          children: renderLinkedImages(child.props.children),
        });
  });
}

type ComparisonCellState = "included" | "excluded" | "neutral";

function getComparisonCellState(value: string): ComparisonCellState | null {
  const normalized = value.trim().toLocaleLowerCase();

  if (
    ["✓", "✔", "yes", "true", "included", "支持", "包含"].includes(normalized)
  ) {
    return "included";
  }
  if (
    ["✗", "✕", "×", "no", "false", "not included", "不支持", "不包含"].includes(
      normalized,
    )
  ) {
    return "excluded";
  }
  if (["—", "–", "-", "n/a", "na"].includes(normalized)) {
    return "neutral";
  }

  return null;
}

function getHeadingAnchorId({
  children,
  headingAnchorContext,
}: {
  children: React.ReactNode;
  headingAnchorContext?: { messageId: string; partIndex: number };
}): string {
  const headingText = extractNodeText(children);

  if (!headingAnchorContext) {
    return createHeadingAnchorId({
      messageId: "standalone",
      partIndex: 0,
      headingText,
    });
  }

  return createHeadingAnchorId({
    messageId: headingAnchorContext.messageId,
    partIndex: headingAnchorContext.partIndex,
    headingText,
  });
}

function InlineCode({ children }: { children: React.ReactNode }) {
  const codeId = useId();
  const { t } = useTranslation();
  const { copied, failed, copying, copy } = useClipboardCopy(String(children));
  const label = t(copied ? "chat.message.copied" : "chat.message.copyCode");
  return (
    <button
      type="button"
      className="rounded bg-theme-bg-code px-1.5 py-0.5 text-14 text-theme-text font-mono cursor-pointer hover:bg-theme-bg-hover transition-colors"
      disabled={copying}
      aria-busy={copying || undefined}
      aria-label={label}
      aria-describedby={failed ? `${codeId} ${codeId}-error` : codeId}
      title={failed ? t("chat.message.copyFailed") : label}
      onClick={(event) => {
        event.stopPropagation();
        void copy();
      }}
    >
      <code id={codeId}>{children}</code>
      {failed && (
        <span id={`${codeId}-error`} className="sr-only">
          {t("chat.message.copyFailed")}
        </span>
      )}
    </button>
  );
}

// Code block component with copy button and enhanced styling
function CodeBlock({
  className,
  children,
  inline,
  isStreaming,
}: {
  className?: string;
  children?: React.ReactNode;
  inline?: boolean;
  isStreaming?: boolean;
}) {
  const { t } = useTranslation();
  const match = /language-(\w+)/.exec(className || "");
  const language = match ? match[1] : "";
  const codeString = String(children).replace(/\n$/, "");

  // Handle mermaid diagrams
  if (language === "mermaid") {
    return <MermaidDiagram chart={codeString} isStreaming={isStreaming} />;
  }

  if (inline) return <InlineCode>{children}</InlineCode>;

  return (
    <div
      className="ai-code-block group relative my-2 sm:my-3 max-w-full overflow-hidden rounded-xl border border-stone-200 dark:border-stone-700"
      data-streaming={isStreaming || undefined}
    >
      {/* Header bar - always visible on touch, hover on desktop */}
      <div className="ai-code-block__header flex items-center justify-between px-3 sm:px-4 py-2 bg-stone-200/70 dark:bg-stone-800/50 font-serif">
        <div className="ai-code-block__file flex items-center gap-2 min-w-0">
          <Code2
            size={14}
            className="ai-code-block__icon shrink-0"
            aria-hidden="true"
          />
          {/* Language label */}
          <span className="ai-code-block__language text-12 font-medium text-stone-500 dark:text-stone-400 truncate">
            {language || "text"}
          </span>
        </div>
        {/* Copy button */}
        <CopyButton
          text={codeString}
          label={t("chat.message.copyCode")}
          className="ai-code-block__copy"
        />
      </div>

      {/* Code content */}
      <div className="ai-code-block__body bg-theme-bg-code [&_.cm-line]:leading-5 [&_.cm-gutterElement]:leading-5 overflow-hidden rounded-b-xl">
        <DeferredCodeMirrorViewer
          value={codeString}
          language={language || undefined}
          lineNumbers={true}
          fontSize="0.75rem"
          className="[&_.cm-editor]:rounded-none [&_.cm-gutters]:border-r-0"
        />
      </div>
    </div>
  );
}

// Table block with copy & export toolbar
function TableBlock({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const tableRef = React.useRef<HTMLTableElement>(null);

  const extractData = (): string[][] => {
    if (!tableRef.current) return [];
    const rows = tableRef.current.querySelectorAll("tr");
    return Array.from(rows).map((row) =>
      Array.from(row.querySelectorAll("th, td")).map(
        (cell) => cell.textContent?.trim() || "",
      ),
    );
  };

  const handleCopy = () => {
    const data = extractData();
    if (data.length === 0) return "";

    const colWidths = data[0].map((_, colIdx) =>
      Math.max(...data.map((row) => (row[colIdx] || "").length)),
    );
    const pad = (str: string, width: number) =>
      str.length < width ? str + " ".repeat(width - str.length) : str;

    const header =
      "| " + data[0].map((c, i) => pad(c, colWidths[i])).join(" | ") + " |";
    const separator =
      "| " + colWidths.map((w) => "-".repeat(w)).join(" | ") + " |";
    const rows = data
      .slice(1)
      .map(
        (row) =>
          "| " + row.map((c, i) => pad(c, colWidths[i])).join(" | ") + " |",
      );

    return [header, separator, ...rows].join("\n");
  };

  const handleExport = () => {
    const data = extractData();
    const csv = data
      .map((row) =>
        row.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(","),
      )
      .join("\r\n");
    const blob = new Blob(["\uFEFF" + csv], {
      type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `table-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="ai-data-table group/table my-3 overflow-hidden">
      {/* Toolbar */}
      <div
        className={clsx(
          "ai-data-table__toolbar flex items-center justify-between px-2.5 py-2 font-serif",
        )}
      >
        <span className="ai-data-table__title flex items-center gap-1.5 text-11 sm:text-12 font-medium select-none">
          <Table2 size={12} aria-hidden="true" />
          {t("chat.message.table", "Table")}
        </span>
        <div className="ai-data-table__actions flex items-center gap-0.5">
          <CopyButton
            text={handleCopy}
            size={12}
            showLabel
            className="ai-data-table__action !gap-1 !px-1.5 !text-11 sm:!text-12"
          />
          <button
            onClick={handleExport}
            className="ai-data-table__action flex items-center gap-1 rounded px-1.5 py-0.5 text-11 sm:text-12 font-medium text-stone-500 dark:text-stone-400 transition-colors"
            aria-label={t("chat.message.exportCsv", "Export CSV")}
            title={t("chat.message.exportCsv", "Export CSV")}
          >
            <Download size={12} />
            {t("chat.message.exportCsv", "CSV")}
          </button>
        </div>
      </div>
      {/* Scrollable table area */}
      <div className="ai-data-table__scroll overflow-x-auto">
        <table ref={tableRef} className="ai-data-table__table min-w-full">
          {children}
        </table>
      </div>
    </div>
  );
}

// Markdown content rendering component - styled version
export const MarkdownContent = memo(function MarkdownContent({
  content,
  isStreaming,
  headingAnchorContext,
}: {
  content: string;
  isStreaming?: boolean;
  headingAnchorContext?: { messageId: string; partIndex: number };
}) {
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);
  const sessionImageGallery = useSessionImageGallery();

  return (
    <span
      className="ai-streaming-text markdown-preview block my-1 pl-0.5"
      data-streaming={isStreaming || undefined}
      aria-busy={isStreaming || undefined}
    >
      <ReactMarkdown
        remarkPlugins={[...cjkGfmRemarkPlugins, remarkBreaks, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // Headings with anchor links
          h1: ({ children }) => {
            const id = getHeadingAnchorId({ children, headingAnchorContext });
            return (
              <h1
                id={id}
                data-outline-anchor="true"
                data-outline-id={id}
                className="text-24 font-bold text-stone-900 dark:text-stone-100 mt-4 mb-3 first:mt-0 group/head scroll-mt-4"
              >
                <a
                  href={`#${id}`}
                  className="no-underline text-inherit hover:text-amber-600 dark:hover:text-amber-400 transition-colors"
                >
                  {children}
                </a>
              </h1>
            );
          },
          h2: ({ children }) => {
            const id = getHeadingAnchorId({ children, headingAnchorContext });
            return (
              <h2
                id={id}
                data-outline-anchor="true"
                data-outline-id={id}
                className="text-20 font-bold text-stone-900 dark:text-stone-100 mt-3 mb-2 group/head scroll-mt-4"
              >
                <a
                  href={`#${id}`}
                  className="no-underline text-inherit hover:text-amber-600 dark:hover:text-amber-400 transition-colors"
                >
                  {children}
                </a>
              </h2>
            );
          },
          h3: ({ children }) => {
            const id = getHeadingAnchorId({ children, headingAnchorContext });
            return (
              <h3
                id={id}
                data-outline-anchor="true"
                data-outline-id={id}
                className="text-18 font-semibold text-stone-900 dark:text-stone-100 mt-2 mb-1.5 group/head scroll-mt-4"
              >
                <a
                  href={`#${id}`}
                  className="no-underline text-inherit hover:text-amber-600 dark:hover:text-amber-400 transition-colors"
                >
                  {children}
                </a>
              </h3>
            );
          },
          h4: ({ children }) => {
            const id = getHeadingAnchorId({ children, headingAnchorContext });
            return (
              <h4
                id={id}
                data-outline-anchor="true"
                data-outline-id={id}
                className="text-16 font-semibold text-stone-800 dark:text-stone-200 mt-2 mb-1 group/head scroll-mt-4"
              >
                <a
                  href={`#${id}`}
                  className="no-underline text-inherit hover:text-amber-600 dark:hover:text-amber-400 transition-colors"
                >
                  {children}
                </a>
              </h4>
            );
          },
          // Paragraphs
          p: ({ children }) => (
            <p className="text-gray-700 dark:text-gray-300 leading-[1.75] mb-2 last:mb-0">
              {children}
            </p>
          ),
          // Lists with better styling
          ul: ({ children }) => (
            <ul className="list-disc space-y-1.5 mb-3 pl-5 marker:text-amber-500 dark:marker:text-amber-400 marker:text-[0.6em]">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside space-y-1.5 mb-3 pl-5 marker:text-stone-500 dark:marker-stone-400 marker:font-semibold">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="text-gray-700 dark:text-gray-300 leading-[1.75]">
              {children}
            </li>
          ),
          // Blockquotes with elegant styling
          blockquote: ({ children }) => (
            <blockquote
              className="my-3 pl-4 pr-3 py-2 border-l-[5px] border-amber-400 bg-amber-50 dark:bg-amber-900/20"
              style={{ borderRadius: "4px" }}
            >
              <div className="text-stone-600 dark:text-stone-300 text-14 [&>p]:italic [&>p:first-child]:italic">
                {children}
              </div>
            </blockquote>
          ),
          // Links with hover effects
          a: ({ href, children }) => {
            const linkChildren = renderLinkedImages(children);
            if (href) {
              const fileLinkInfo = getFileLinkInfo(
                href,
                extractNodeText(children),
              );
              if (fileLinkInfo.isFile && shouldInterceptFilePreviewLink(href)) {
                return (
                  <a
                    href={href}
                    className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 hover:underline transition-colors cursor-pointer"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      const fullUrl = getFullUrl(href) || href;
                      setActiveRevealPreviewState(
                        createActiveRevealPreviewState(
                          {
                            kind: "file",
                            previewKey: fullUrl,
                            filePath: fileLinkInfo.fileName,
                            signedUrl: fullUrl,
                          },
                          "manual",
                        ),
                      );
                    }}
                  >
                    {linkChildren}
                  </a>
                );
              }
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 hover:underline transition-colors"
              >
                {linkChildren}
              </a>
            );
          },
          // Horizontal rule
          hr: () => (
            <hr className="my-4 border-0 h-px bg-gradient-to-r from-transparent via-stone-300 to-transparent dark:via-stone-600" />
          ),
          // Strong and emphasis
          strong: ({ children }) => (
            <strong className="font-bold text-stone-900 dark:text-stone-100">
              {children}
            </strong>
          ),
          em: ({ children }) => (
            <em className="italic text-stone-600 dark:text-stone-400">
              {children}
            </em>
          ),
          // Code blocks
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          code: (props: any) => {
            const { className, children, isInPre } = props;
            const hasLanguage = className && /language-/.test(className);
            const isInline = !isInPre && !hasLanguage;

            return (
              <CodeBlock
                className={className}
                inline={isInline}
                isStreaming={isStreaming}
              >
                {children}
              </CodeBlock>
            );
          },
          pre: ({ children }) => {
            if (React.isValidElement(children)) {
              return React.cloneElement(
                children as React.ReactElement<{ isInPre?: boolean }>,
                { isInPre: true },
              );
            }
            return <>{children}</>;
          },
          // Tables with copy & export toolbar
          table: ({ children }) => <TableBlock>{children}</TableBlock>,
          thead: ({ children }) => (
            <thead className="ai-data-table__head">{children}</thead>
          ),
          tbody: ({ children }) => (
            <tbody className="ai-data-table__body">{children}</tbody>
          ),
          tr: ({ children }) => (
            <tr className="ai-data-table__row">{children}</tr>
          ),
          th: ({ children }) => (
            <th className="ai-data-table__header-cell">{children}</th>
          ),
          td: ({ children }) => {
            const cellText = extractNodeText(children).trim();
            const comparisonState = getComparisonCellState(cellText);
            const ComparisonIcon =
              comparisonState === "included"
                ? Check
                : comparisonState === "excluded"
                  ? X
                  : Minus;

            return (
              <td
                className="ai-data-table__cell"
                data-comparison-state={comparisonState || undefined}
              >
                {comparisonState ? (
                  <span className="ai-comparison-value">
                    <ComparisonIcon
                      size={13}
                      strokeWidth={2.25}
                      aria-hidden="true"
                    />
                    <span className="sr-only">{cellText}</span>
                  </span>
                ) : (
                  children
                )}
              </td>
            );
          },
          // Images — click to preview with ImageViewer
          img: ({ src, alt }) => {
            const resolvedSrc = getFullUrl(src);
            return (
              <ImageWithSkeleton
                src={resolvedSrc}
                thumbSrc={buildChatThumbUrl(resolvedSrc)}
                alt={alt}
                loading="eager"
                className="max-w-lg h-auto rounded-lg shadow hover:opacity-90 transition-opacity cursor-zoom-in"
                onClick={() => {
                  if (!resolvedSrc) return;
                  sessionImageGallery?.openImage(resolvedSrc, alt || undefined);
                  if (!sessionImageGallery) {
                    setImageViewerSrc(resolvedSrc);
                  }
                }}
              />
            );
          },
        }}
      >
        {normalizeMarkdownCodeFences(content)}
      </ReactMarkdown>

      {/* Image preview lightbox */}
      <ImageViewer
        src={imageViewerSrc || ""}
        isOpen={!!imageViewerSrc}
        onClose={() => setImageViewerSrc(null)}
      />
    </span>
  );
});

// eslint-disable-next-line react-refresh/only-export-components
export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "...";
}
