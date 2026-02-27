import { memo, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import {
  oneDark,
  oneLight,
} from "react-syntax-highlighter/dist/esm/styles/prism";
import MermaidDiagram from "./MermaidDiagram";

interface MarkdownRendererProps {
  content: string;
  t: (key: string, options?: Record<string, unknown>) => string;
}

// Memoized markdown renderer with enhanced styling
const MarkdownRenderer = memo(function MarkdownRenderer({
  content,
  t,
}: MarkdownRendererProps) {
  // Limit content for very large files
  const displayContent = useMemo(() => {
    const maxChars = 100000;
    if (content.length > maxChars) {
      return (
        content.slice(0, maxChars) + `\n\n${t("documents.fileTooLargeChars")}`
      );
    }
    return content;
  }, [content, t]);

  // Detect dark mode
  const [isDark, setIsDark] = useState(() =>
    typeof window !== "undefined"
      ? document.documentElement.classList.contains("dark")
      : true,
  );

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains("dark"));
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  return (
    <div className="markdown-preview overflow-auto h-full">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // Headings with anchor styling
          h1: ({ children }) => (
            <h1 className="text-3xl font-bold text-stone-900 dark:text-stone-100 mt-8 mb-4 pb-3 border-b-2 border-stone-200 dark:border-stone-700 first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-2xl font-bold text-stone-900 dark:text-stone-100 mt-6 mb-3 pb-2 border-b border-stone-200 dark:border-stone-700">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 mt-5 mb-2">
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-lg font-semibold text-stone-800 dark:text-stone-200 mt-4 mb-2">
              {children}
            </h4>
          ),
          // Paragraphs
          p: ({ children }) => (
            <p className="text-stone-700 dark:text-stone-300 leading-relaxed mb-4 last:mb-0">
              {children}
            </p>
          ),
          // Lists with better styling
          ul: ({ children }) => (
            <ul className="list-none space-y-2 mb-4 pl-6">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal space-y-2 mb-4 pl-6 marker:text-stone-500 dark:marker-stone-400 marker:font-semibold">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="text-stone-700 dark:text-stone-300 leading-relaxed relative">
              <span className="absolute -left-4 top-2 w-1.5 h-1.5 rounded-full bg-amber-500" />
              {children}
            </li>
          ),
          // Blockquotes with elegant styling
          blockquote: ({ children }) => (
            <blockquote className="my-4 pl-4 pr-4 py-3 border-l-4 border-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded-r-lg">
              <div className="text-stone-600 dark:text-stone-300 italic">
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
            <hr className="my-6 border-0 h-px bg-gradient-to-r from-transparent via-stone-300 dark:via-stone-600 to-transparent" />
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
          // Code blocks with language detection
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "");
            const language = match ? match[1] : "";
            const isInline = !match;
            const codeContent = String(children).replace(/\n$/, "");

            // Handle Mermaid diagrams
            if (language === "mermaid") {
              return <MermaidDiagram code={codeContent} t={t} />;
            }

            // Inline code
            if (isInline) {
              return (
                <code
                  className="px-2 py-0.5 rounded-md bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300 font-mono text-sm font-medium"
                  {...props}
                >
                  {children}
                </code>
              );
            }

            // Code block with syntax highlighting
            return (
              <div className="my-4 rounded-xl overflow-hidden shadow-lg ring-1 ring-stone-200 dark:ring-stone-700">
                {language && (
                  <div className="flex items-center gap-2 px-4 py-2 bg-stone-800 dark:bg-stone-900 text-stone-300 text-xs font-medium">
                    <span className="w-2 h-2 rounded-full bg-red-500" />
                    <span className="w-2 h-2 rounded-full bg-yellow-500" />
                    <span className="w-2 h-2 rounded-full bg-green-500" />
                    <span className="ml-2 uppercase tracking-wide">
                      {language}
                    </span>
                  </div>
                )}
                <SyntaxHighlighter
                  style={isDark ? oneDark : oneLight}
                  language={language || "text"}
                  customStyle={{
                    margin: 0,
                    padding: "1rem",
                    background: isDark ? "#1e1e1e" : "#fafafa",
                    fontSize: "0.875rem",
                    lineHeight: "1.6",
                  }}
                  showLineNumbers
                  lineNumberStyle={{
                    minWidth: "2.5em",
                    paddingRight: "1em",
                    textAlign: "right",
                    color: isDark ? "#6b7280" : "#9ca3af",
                    userSelect: "none",
                    fontSize: "0.75rem",
                  }}
                  wrapLines={false}
                  wrapLongLines={false}
                >
                  {codeContent}
                </SyntaxHighlighter>
              </div>
            );
          },
          // Tables with beautiful styling
          table: ({ children }) => (
            <div className="my-4 overflow-x-auto rounded-lg shadow ring-1 ring-stone-200 dark:ring-stone-700">
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
            <th className="px-4 py-3 text-left text-xs font-semibold text-stone-700 dark:text-stone-300 uppercase tracking-wider">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-4 py-3 text-sm text-stone-600 dark:text-stone-400 whitespace-nowrap">
              {children}
            </td>
          ),
          // Images with shadow
          img: ({ src, alt }) => (
            <img
              src={src}
              alt={alt}
              className="max-w-full h-auto my-4 rounded-lg shadow-lg"
            />
          ),
        }}
      >
        {displayContent}
      </ReactMarkdown>
    </div>
  );
});

export default MarkdownRenderer;
