import ReactMarkdown from "react-markdown";
import toast from "react-hot-toast";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import React, { memo, useState } from "react";
import { Copy, Check, Download, Table2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { getFullUrl } from "../../../services/api/config";
import { MermaidDiagram } from "./MermaidDiagram";
import { DeferredCodeMirrorViewer } from "../../common/DeferredCodeMirrorViewer";
import { ImageViewer } from "../../common";
import { createHeadingAnchorId } from "../../layout/AppContent/messageOutline";
import { getFileLinkInfo } from "../../documents/utils";
import { setActiveRevealPreviewState } from "./items/activeRevealPreviewStore";
import { createActiveRevealPreviewState } from "./items/revealPreviewState";
import { shouldInterceptFilePreviewLink } from "./items/revealPreviewLinks";
import { copyToClipboard } from "../../../utils/clipboard";
import { useSessionImageGallery } from "./sessionImageGallery";
import { ImageWithSkeleton } from "./ImageWithSkeleton";
import { normalizeMarkdownCodeFences } from "./markdownCodeFences";

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
  const [copied, setCopied] = React.useState(false);
  const match = /language-(\w+)/.exec(className || "");
  const language = match ? match[1] : "";
  const codeString = String(children).replace(/\n$/, "");

  const handleCopy = async () => {
    await copyToClipboard(codeString);
    setCopied(true);
    toast.success(t("chat.message.copied"));
    setTimeout(() => setCopied(false), 2000);
  };

  // Handle mermaid diagrams
  if (language === "mermaid") {
    return <MermaidDiagram chart={codeString} isStreaming={isStreaming} />;
  }

  if (inline) {
    return (
      <code
        className="rounded bg-stone-200 dark:bg-stone-700 px-1.5 py-0.5 text-sm text-stone-800 dark:text-stone-200 font-mono cursor-pointer hover:bg-stone-300 dark:hover:bg-stone-600 transition-colors"
        onClick={() => {
          copyToClipboard(String(children));
          toast.success(t("chat.message.copied"));
        }}
        title={t("chat.message.copyCode")}
      >
        {children}
      </code>
    );
  }

  return (
    <div className="group relative my-2 sm:my-3 max-w-full overflow-hidden rounded-xl border border-stone-200 dark:border-stone-700">
      {/* Header bar - always visible on touch, hover on desktop */}
      <div className="flex items-center justify-between px-3 sm:px-4 py-2 bg-stone-200/70 dark:bg-stone-800/50">
        <div className="flex items-center gap-2 min-w-0">
          {/* Language label */}
          <span className="text-xs font-medium text-stone-500 dark:text-stone-400 truncate">
            {language || "text"}
          </span>
        </div>
        {/* Copy button */}
        <button
          onClick={handleCopy}
          className={clsx(
            "flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all touch-manipulation",
            "min-h-[32px] min-w-[32px]",
            copied
              ? "text-green-600 dark:text-green-400"
              : "text-stone-500 hover:text-stone-700 hover:bg-stone-300/50 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/50",
          )}
          title={copied ? t("chat.message.copied") : t("chat.message.copyCode")}
        >
          {copied ? (
            <>
              <Check size={14} />
              <span className="hidden xs:inline">
                {t("chat.message.copied")}
              </span>
            </>
          ) : (
            <>
              <Copy size={14} />
              <span className="hidden xs:inline">{t("chat.message.copy")}</span>
            </>
          )}
        </button>
      </div>

      {/* Code content */}
      <div className="bg-white dark:bg-[#282c34] [&_.cm-line]:leading-5 [&_.cm-gutterElement]:leading-5 overflow-hidden rounded-b-xl">
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
  const [copied, setCopied] = React.useState(false);
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

  const handleCopy = async () => {
    const data = extractData();
    if (data.length === 0) return;

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

    const markdown = [header, separator, ...rows].join("\n");
    await copyToClipboard(markdown);
    setCopied(true);
    toast.success(t("chat.message.copied"));
    setTimeout(() => setCopied(false), 2000);
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
    <div className="group/table my-3 rounded-lg shadow ring-1 ring-stone-200 dark:ring-stone-700 overflow-hidden">
      {/* Toolbar */}
      <div
        className={clsx(
          "flex items-center justify-between px-2 py-1.5",
          "border-b border-stone-200/60 dark:border-stone-700/60",
          "bg-stone-50/80 dark:bg-stone-800/60",
        )}
      >
        <span className="flex items-center gap-1.5 text-[11px] sm:text-xs font-medium text-stone-500 dark:text-stone-400 select-none">
          <Table2 size={12} />
          {t("chat.message.table", "Table")}
        </span>
        <div className="flex items-center gap-0.5">
          <button
            onClick={handleCopy}
            className={clsx(
              "flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] sm:text-xs font-medium transition-colors",
              copied
                ? "text-green-600 dark:text-green-400"
                : "text-stone-500 hover:text-stone-700 hover:bg-stone-200/60 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/50",
            )}
            title={copied ? t("chat.message.copied") : t("chat.message.copy")}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? t("chat.message.copied") : t("chat.message.copy")}
          </button>
          <button
            onClick={handleExport}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] sm:text-xs font-medium text-stone-500 hover:text-stone-700 hover:bg-stone-200/60 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/50 transition-colors"
            title={t("chat.message.exportCsv", "Export CSV")}
          >
            <Download size={12} />
            {t("chat.message.exportCsv", "CSV")}
          </button>
        </div>
      </div>
      {/* Scrollable table area */}
      <div className="overflow-x-auto">
        <table
          ref={tableRef}
          className="min-w-full divide-y divide-stone-200 dark:divide-stone-700"
        >
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
    <span className="markdown-preview block my-1 pl-0.5">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks, remarkMath]}
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
                className="text-2xl font-bold text-stone-900 dark:text-stone-100 mt-4 mb-3 first:mt-0 group/head scroll-mt-4"
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
                className="text-xl font-bold text-stone-900 dark:text-stone-100 mt-3 mb-2 group/head scroll-mt-4"
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
                className="text-lg font-semibold text-stone-900 dark:text-stone-100 mt-2 mb-1.5 group/head scroll-mt-4"
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
                className="text-base font-semibold text-stone-800 dark:text-stone-200 mt-2 mb-1 group/head scroll-mt-4"
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
              <div className="text-stone-600 dark:text-stone-300 text-sm [&>p]:italic [&>p:first-child]:italic">
                {children}
              </div>
            </blockquote>
          ),
          // Links with hover effects
          a: ({ href, children }) => {
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
                    {children}
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
                {children}
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
            <thead className="bg-stone-50 dark:bg-stone-800">{children}</thead>
          ),
          tbody: ({ children }) => (
            <tbody className="divide-y divide-stone-200 dark:divide-stone-700 bg-white dark:bg-stone-900">
              {children}
            </tbody>
          ),
          tr: ({ children }) => (
            <tr className="hover:bg-stone-50 dark:hover:bg-stone-800/50 transition-colors">
              {children}
            </tr>
          ),
          th: ({ children }) => (
            <th className="px-2 sm:px-3 py-1.5 sm:py-2 text-left text-[11px] sm:text-xs font-semibold text-stone-700 dark:text-stone-300 uppercase tracking-wider whitespace-nowrap min-w-[40px]">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-2 sm:px-3 py-1.5 sm:py-2 text-xs sm:text-sm text-stone-600 dark:text-stone-400 break-words min-w-[60px]">
              {children}
            </td>
          ),
          // Images — click to preview with ImageViewer
          img: ({ src, alt }) => {
            const resolvedSrc = getFullUrl(src);
            return (
              <ImageWithSkeleton
                src={resolvedSrc}
                alt={alt}
                loading="eager"
                className="max-w-full h-auto rounded-lg shadow hover:opacity-90 transition-opacity"
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
