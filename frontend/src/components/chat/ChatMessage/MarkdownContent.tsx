import ReactMarkdown, { type Components } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import React, {
  createContext,
  useContext,
  useCallback,
  memo,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { Check, Download, Table2, Code2, X, Minus } from "lucide-react";
import { useTranslation } from "react-i18next";
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

type MarkdownContextValue = {
  isStreaming?: boolean;
  headingAnchorContext?: { messageId: string; partIndex: number };
  openImage: (src: string) => void;
};

const MarkdownContext = createContext<MarkdownContextValue>({
  openImage: () => {},
});

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
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [insideLink, setInsideLink] = useState(false);
  useEffect(() => {
    // A copy <button> nested in an <a> is invalid HTML and double-interactive;
    // inline code inside links stays a plain, non-interactive <code>.
    setInsideLink(!!buttonRef.current?.closest("a"));
  }, []);
  if (insideLink) {
    return <code className="markdown-inline-code">{children}</code>;
  }
  return (
    <button
      ref={buttonRef}
      type="button"
      className="markdown-inline-code-copy"
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
      <code id={codeId} className="markdown-inline-code">
        {children}
      </code>
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
      {/* Code content */}
      <div className="ai-code-block__body bg-theme-bg-code [&_.cm-line]:leading-5 [&_.cm-gutterElement]:leading-5 overflow-hidden rounded-b-xl">
        <DeferredCodeMirrorViewer
          value={codeString}
          language={language || undefined}
          lineNumbers={true}
          fontSize="0.8125rem"
          className="[&_.cm-editor]:rounded-none [&_.cm-gutters]:border-r-0"
          copyable
          simpleSearch
          copyLabel={t("chat.message.copyCode")}
          toolbarLabel={
            <div className="ai-code-block__file flex items-center gap-2 min-w-0">
              <Code2
                size={14}
                className="ai-code-block__icon shrink-0"
                aria-hidden="true"
              />
              <span className="ai-code-block__language text-12 font-medium truncate">
                {language || "text"}
              </span>
            </div>
          }
        />
      </div>
    </div>
  );
}

// Table block with copy & export toolbar
function TableBlock({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const tableRef = React.useRef<HTMLTableElement>(null);

  const extractData = useCallback((): string[][] => {
    if (!tableRef.current) return [];
    const rows = tableRef.current.querySelectorAll("tr");
    return Array.from(rows).map((row) =>
      Array.from(row.querySelectorAll("th, td")).map(
        (cell) => cell.textContent?.trim() || "",
      ),
    );
  }, []);

  const handleCopy = useCallback(() => {
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
  }, [extractData]);

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
      <div className="ai-data-table__toolbar flex items-center justify-between px-3 py-2">
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

// Stable node components preserve interactive state while Markdown grows.
const markdownComponents: Components = {
  // Headings with anchor links
  h1: function Heading1({ children }) {
    const { headingAnchorContext } = useContext(MarkdownContext);
    const id = getHeadingAnchorId({ children, headingAnchorContext });
    return (
      <h1
        id={id}
        data-outline-anchor="true"
        data-outline-id={id}
        className="scroll-mt-4"
      >
        <a
          href={`#${id}`}
          className="markdown-heading-link"
        >
          {children}
        </a>
      </h1>
    );
  },
  h2: function Heading2({ children }) {
    const { headingAnchorContext } = useContext(MarkdownContext);
    const id = getHeadingAnchorId({ children, headingAnchorContext });
    return (
      <h2
        id={id}
        data-outline-anchor="true"
        data-outline-id={id}
        className="scroll-mt-4"
      >
        <a
          href={`#${id}`}
          className="markdown-heading-link"
        >
          {children}
        </a>
      </h2>
    );
  },
  h3: function Heading3({ children }) {
    const { headingAnchorContext } = useContext(MarkdownContext);
    const id = getHeadingAnchorId({ children, headingAnchorContext });
    return (
      <h3
        id={id}
        data-outline-anchor="true"
        data-outline-id={id}
        className="scroll-mt-4"
      >
        <a
          href={`#${id}`}
          className="markdown-heading-link"
        >
          {children}
        </a>
      </h3>
    );
  },
  h4: function Heading4({ children }) {
    const { headingAnchorContext } = useContext(MarkdownContext);
    const id = getHeadingAnchorId({ children, headingAnchorContext });
    return (
      <h4
        id={id}
        data-outline-anchor="true"
        data-outline-id={id}
        className="scroll-mt-4"
      >
        <a
          href={`#${id}`}
          className="markdown-heading-link"
        >
          {children}
        </a>
      </h4>
    );
  },
  h5: function Heading5({ children }) {
    const { headingAnchorContext } = useContext(MarkdownContext);
    const id = getHeadingAnchorId({ children, headingAnchorContext });
    return (
      <h5
        id={id}
        data-outline-anchor="true"
        data-outline-id={id}
        className="scroll-mt-4"
      >
        <a
          href={`#${id}`}
          className="markdown-heading-link"
        >
          {children}
        </a>
      </h5>
    );
  },
  h6: function Heading6({ children }) {
    const { headingAnchorContext } = useContext(MarkdownContext);
    const id = getHeadingAnchorId({ children, headingAnchorContext });
    return (
      <h6
        id={id}
        data-outline-anchor="true"
        data-outline-id={id}
        className="scroll-mt-4"
      >
        <a
          href={`#${id}`}
          className="markdown-heading-link"
        >
          {children}
        </a>
      </h6>
    );
  },
  // Typography is shared by chat and document previews in markdown.css.
  p: ({ children }) => <p>{children}</p>,
  ul: ({ children, className }) => <ul className={className}>{children}</ul>,
  ol: ({ children, start }) => <ol start={start}>{children}</ol>,
  li: ({ children, className }) => <li className={className}>{children}</li>,
  blockquote: ({ children }) => <blockquote>{children}</blockquote>,
  // Links with hover effects
  a: ({ href, children }) => {
    const linkChildren = renderLinkedImages(children);
    if (href) {
      const fileLinkInfo = getFileLinkInfo(href, extractNodeText(children));
      if (fileLinkInfo.isFile && shouldInterceptFilePreviewLink(href)) {
        return (
          <a
            href={href}
            className="markdown-link"
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
        className="markdown-link"
      >
        {linkChildren}
      </a>
    );
  },
  hr: () => <hr />,
  strong: ({ children }) => <strong>{children}</strong>,
  em: ({ children }) => <em>{children}</em>,
  // Code blocks
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  code: function MarkdownCode(props: any) {
    const { isStreaming } = useContext(MarkdownContext);
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
  tr: ({ children }) => <tr className="ai-data-table__row">{children}</tr>,
  th: ({ children, style }) => (
    <th className="ai-data-table__header-cell" style={style}>{children}</th>
  ),
  td: ({ children, style }) => {
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
        style={comparisonState ? { ...style, textAlign: "center" } : style}
        data-comparison-state={comparisonState || undefined}
      >
        {comparisonState ? (
          <span className="ai-comparison-value">
            <ComparisonIcon size={13} strokeWidth={2.25} aria-hidden="true" />
            <span className="sr-only">{cellText}</span>
          </span>
        ) : (
          children
        )}
      </td>
    );
  },
  // Images — click to preview with ImageViewer
  img: function MarkdownImage({ src, alt }) {
    const { openImage } = useContext(MarkdownContext);
    const sessionImageGallery = useSessionImageGallery();
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
            openImage(resolvedSrc);
          }
        }}
      />
    );
  },
};

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
  return (
    <MarkdownContext.Provider
      value={{
        isStreaming,
        headingAnchorContext,
        openImage: setImageViewerSrc,
      }}
    >
      <span
        className="ai-streaming-text markdown-preview markdown-prose block my-1"
        data-streaming={isStreaming || undefined}
        aria-busy={isStreaming || undefined}
      >
        <ReactMarkdown
          remarkPlugins={[...cjkGfmRemarkPlugins, remarkBreaks, remarkMath]}
          rehypePlugins={[rehypeKatex]}
          components={markdownComponents}
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
    </MarkdownContext.Provider>
  );
});

// eslint-disable-next-line react-refresh/only-export-components
export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "...";
}
