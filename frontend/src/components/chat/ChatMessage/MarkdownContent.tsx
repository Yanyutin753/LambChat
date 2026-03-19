import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import {
  oneLight,
  oneDark,
} from "react-syntax-highlighter/dist/esm/styles/prism";
import React, { useEffect, useState, memo } from "react";
import { Copy, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { MermaidDiagram } from "./MermaidDiagram";

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
  const [copied, setCopied] = useState(false);
  const [isDark, setIsDark] = useState(false);
  const match = /language-(\w+)/.exec(className || "");
  const language = match ? match[1] : "";
  const codeString = String(children).replace(/\n$/, "");

  // Detect dark mode
  useEffect(() => {
    const checkDark = () => {
      setIsDark(document.documentElement.classList.contains("dark"));
    };
    checkDark();
    const observer = new MutationObserver(checkDark);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(codeString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Handle mermaid diagrams
  if (language === "mermaid") {
    return <MermaidDiagram chart={codeString} isStreaming={isStreaming} />;
  }

  if (inline) {
    return (
      <code className="rounded bg-stone-200 dark:bg-stone-700 px-1.5 py-0.5 text-sm text-stone-800 dark:text-stone-200 font-mono">
        {children}
      </code>
    );
  }

  // Split code into lines for line numbers
  const codeLines = codeString.split("\n");

  return (
    <div className="group relative my-2 sm:my-3 max-w-full overflow-hidden rounded-xl border border-stone-200 dark:border-stone-700">
      {/* Header bar - ChatGPT style */}
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
      {language ? (
        (() => {
          const digits = String(codeLines.length).length;
          const lineNumWidth = `${Math.max(digits, 3) + 1}em`;
          return (
        <SyntaxHighlighter
          language={language}
          style={isDark ? oneDark : oneLight}
          showLineNumbers={true}
          wrapLines={true}
          customStyle={{
            margin: 0,
            padding: "0.75rem",
            fontSize: "0.75rem",
            lineHeight: "1.7",
            background: "transparent",
          }}
          lineNumberStyle={{
            minWidth: lineNumWidth,
            width: lineNumWidth,
            paddingRight: "1em",
            textAlign: "right",
            color: isDark ? "#71717a" : "#a1a1aa",
            borderRight: isDark ? "1px solid #44403c" : "1px solid #e7e5e4",
            userSelect: "none",
          }}
          codeTagProps={{
            style: {
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            },
          }}
        >
          {codeString}
        </SyntaxHighlighter>
          );
        })()
      ) : (
        /* Plain code block without syntax highlighting (no language specified) */
        (() => {
          const digits = String(codeLines.length).length;
          const lineNumWidth = `${Math.max(digits, 3) + 1}em`;
          return (
        <div className="overflow-x-auto">
          <pre
            className="p-3 text-xs leading-relaxed font-mono"
            style={{
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
              margin: 0,
              fontSize: "0.75rem",
              lineHeight: "1.7",
            }}
          >
            <code>
              {codeLines.map((line, i) => (
                <div key={i} className="flex">
                  <span
                    className="select-none shrink-0 text-right pr-4 mr-4"
                    style={{
                      minWidth: lineNumWidth,
                      width: lineNumWidth,
                      color: isDark ? "#71717a" : "#a1a1aa",
                      borderRight: isDark
                        ? "1px solid #44403c"
                        : "1px solid #e7e5e4",
                      userSelect: "none",
                    }}
                  >
                    {i + 1}
                  </span>
                  <span className="whitespace-pre">{line}</span>
                </div>
              ))}
            </code>
          </pre>
        </div>
          );
        })()
      )}
    </div>
  );
}

// Markdown content rendering component - styled version
export const MarkdownContent = memo(function MarkdownContent({
  content,
  isStreaming,
}: {
  content: string;
  isStreaming?: boolean;
}) {
  return (
    <span className="markdown-preview block my-1">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // Headings
          h1: ({ children }) => (
            <h1 className="text-2xl font-bold text-stone-900 dark:text-stone-100 mt-4 mb-3 first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-xl font-bold text-stone-900 dark:text-stone-100 mt-3 mb-2">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100 mt-2 mb-1.5">
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-base font-semibold text-stone-800 dark:text-stone-200 mt-2 mb-1">
              {children}
            </h4>
          ),
          // Paragraphs
          p: ({ children }) => (
            <p className="text-stone-700 dark:text-stone-300 leading-relaxed mb-2 last:mb-0">
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
            <ol className="list-decimal space-y-1.5 mb-3 pl-5 marker:text-stone-500 dark:marker-stone-400 marker:font-semibold">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="text-stone-700 dark:text-stone-300 leading-relaxed">
              {children}
            </li>
          ),
          // Blockquotes with elegant styling
          blockquote: ({ children }) => (
            <blockquote className="my-3 pl-3 pr-3 py-2 border-l-4 border-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded-r-lg">
              <div className="text-stone-600 dark:text-stone-300 italic text-sm">
                {children}
              </div>
            </blockquote>
          ),
          // Links with hover effects
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 no-underline transition-colors"
            >
              {children}
            </a>
          ),
          // Horizontal rule
          hr: () => (
            <hr className="my-4 border-0 h-px bg-gradient-to-r from-transparent via-stone-300 dark:via-stone-600 to-transparent" />
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
          // Tables with beautiful styling
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto rounded-lg shadow ring-1 ring-stone-200 dark:ring-stone-700">
              <table className="min-w-full divide-y divide-stone-200 dark:divide-stone-700">
                {children}
              </table>
            </div>
          ),
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
            <th className="px-3 py-2 text-left text-xs font-semibold text-stone-700 dark:text-stone-300 uppercase tracking-wider whitespace-nowrap min-w-[60px]">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2 text-sm text-stone-600 dark:text-stone-400 whitespace-nowrap min-w-[60px]">
              {children}
            </td>
          ),
          // Images
          img: ({ src, alt }) => (
            <img
              src={src}
              alt={alt}
              className="max-w-full h-auto my-2 rounded-lg shadow"
            />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
      {isStreaming && (
        <span className="inline-block h-4 w-1.5 animate-pulse bg-amber-400 ml-0.5 rounded-sm align-middle" />
      )}
    </span>
  );
});

// eslint-disable-next-line react-refresh/only-export-components
export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "...";
}
