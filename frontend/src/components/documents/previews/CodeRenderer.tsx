import { memo, useEffect, useMemo, useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import {
  oneDark,
  oneLight,
} from "react-syntax-highlighter/dist/esm/styles/prism";

interface CodeRendererProps {
  content: string;
  language: string;
  t: (key: string, options?: Record<string, unknown>) => string;
}

// Memoized code renderer for better performance
const CodeRenderer = memo(function CodeRenderer({
  content,
  language,
  t,
}: CodeRendererProps) {
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

  // Limit content for very large files to prevent performance issues
  const displayContent = useMemo(() => {
    const maxLines = 5000;
    const lines = content.split("\n");
    if (lines.length > maxLines) {
      return (
        lines.slice(0, maxLines).join("\n") +
        `\n\n${t("documents.fileTooLargeLines", { count: maxLines })}`
      );
    }
    return content;
  }, [content, t]);

  // Dynamic line number width based on total line count
  const lineNumWidth = useMemo(() => {
    const lines = displayContent.split("\n").length;
    const digits = String(lines).length;
    return `${Math.max(digits, 3) + 1}em`;
  }, [displayContent]);

  return (
    <div className="relative h-full overflow-auto bg-stone-100 dark:bg-[#282c34]">
      <SyntaxHighlighter
        language={language}
        style={isDark ? oneDark : oneLight}
        customStyle={{
          margin: 0,
          padding: "1rem",
          background: "transparent",
          fontSize: "0.875rem",
          lineHeight: "1.5",
        }}
        showLineNumbers
        lineNumberStyle={{
          minWidth: lineNumWidth,
          width: lineNumWidth,
          paddingRight: "1em",
          textAlign: "right",
          color: isDark ? "#6b7280" : "#9ca3af",
          userSelect: "none",
          borderRight: isDark ? "1px solid #44403c" : "1px solid #e7e5e4",
        }}
        codeTagProps={{
          style: {
            fontFamily:
              'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
          },
        }}
        wrapLines={false}
        wrapLongLines={false}
      >
        {displayContent}
      </SyntaxHighlighter>
    </div>
  );
});

export default CodeRenderer;
