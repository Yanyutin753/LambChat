import { memo, useState, useEffect } from "react";
import { Code, Eye } from "lucide-react";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { useTranslation } from "react-i18next";
import MarkdownRenderer from "./MarkdownRenderer";

interface MarkdownPreviewProps {
  content: string;
  t: (key: string, options?: Record<string, unknown>) => string;
}

const MarkdownPreview = memo(function MarkdownPreview({
  content,
  t,
}: MarkdownPreviewProps) {
  const { t: t2 } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [showSource, setShowSource] = useState(false);

  useEffect(() => {
    if (content) {
      setLoading(false);
    }
  }, [content]);

  const toggleSource = () => {
    setShowSource(!showSource);
  };

  if (loading) {
    return (
      <div className="h-full w-full flex flex-col bg-white dark:bg-stone-900">
        <div className="flex-1 flex items-center justify-center">
          <LoadingSpinner size="lg" className="text-blue-500" />
          <span className="ml-2 text-stone-500 dark:text-stone-400">
            {t("documents.loadingFileContent")}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full flex flex-col bg-white dark:bg-stone-900">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-white dark:bg-stone-900 border-b border-stone-200 dark:border-stone-700 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-sm text-stone-500 dark:text-stone-400">
            Markdown
          </span>
          <span className="text-xs text-stone-400 dark:text-stone-500">
            ({t("documents.chars", { count: content.length })})
          </span>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={toggleSource}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              showSource
                ? "bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300"
                : "hover:bg-stone-100 dark:hover:bg-stone-800 text-stone-500 dark:text-stone-400"
            }`}
            title={
              showSource
                ? t("documents.previewMode")
                : t("documents.viewSource")
            }
          >
            {showSource ? (
              <>
                <Eye size={14} />
                <span>{t("documents.preview")}</span>
              </>
            ) : (
              <>
                <Code size={14} />
                <span>{t("documents.source")}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {showSource ? (
          <SourceView content={content} t={t} />
        ) : (
          <div className="p-4 sm:p-6 lg:p-8 overflow-auto h-full">
            <MarkdownRenderer content={content} t={t} />
          </div>
        )}
      </div>
    </div>
  );
});

/**
 * Source code view with fixed-width line number column
 * so all content stays aligned regardless of digit count.
 */
function SourceView({
  content,
  t,
}: {
  content: string;
  t: (key: string, options?: Record<string, unknown>) => string;
}) {
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

  const lines = content.split("\n");
  const lineNumWidth = String(lines.length).length;
  const padWidth = Math.max(lineNumWidth, 3); // minimum 3 chars for alignment

  return (
    <div className="w-full h-full overflow-auto bg-stone-100 dark:bg-[#282c34]">
      <pre className="text-sm leading-relaxed" style={{ fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace', margin: 0, padding: "1rem 1rem 1rem 0" }}>
        <code>
          {lines.map((line, i) => (
            <div key={i} className="flex hover:bg-stone-200/50 dark:hover:bg-white/5">
              {/* Fixed-width line number column */}
              <span
                className="inline-block shrink-0 select-none text-right pr-4 pl-4"
                style={{
                  minWidth: `${padWidth + 2}ch`,
                  color: isDark ? "#6b7280" : "#9ca3af",
                  fontSize: "0.75rem",
                  lineHeight: "1.6",
                  // Add a vertical separator line
                  borderRight: `1px solid ${isDark ? "#3e4451" : "#e1e4e8"}`,
                  marginRight: "1rem",
                }}
              >
                {i + 1}
              </span>
              {/* Code content */}
              <span
                className="flex-1 whitespace-pre"
                style={{
                  color: isDark ? "#abb2bf" : "#24292e",
                  lineHeight: "1.6",
                }}
              >
                {line || " "}
              </span>
            </div>
          ))}
        </code>
      </pre>
    </div>
  );
}

export default MarkdownPreview;
