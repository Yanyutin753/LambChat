import { memo, useState, useEffect } from "react";
import { Code, Eye } from "lucide-react";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { useTranslation } from "react-i18next";

interface HtmlPreviewProps {
  content: string; // HTML content directly
}

const HtmlPreview = memo(function HtmlPreview({ content }: HtmlPreviewProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [showSource, setShowSource] = useState(false);

  useEffect(() => {
    if (content) {
      setLoading(false);
    }
  }, [content]);

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
      <div className="flex items-center justify-between px-3 py-1.5 bg-stone-50 dark:bg-stone-900 border-b border-stone-200 dark:border-stone-700 shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
          <span className="text-xs text-stone-500 dark:text-stone-400">
            {t("documents.htmlDocument")}
          </span>
          <span className="text-[11px] text-stone-400 dark:text-stone-500 tabular-nums">
            {content.length.toLocaleString()} chars
          </span>
        </div>

        <div className="flex items-center gap-0.5 bg-stone-100 dark:bg-stone-800 rounded-md p-0.5">
          <button
            onClick={() => setShowSource(false)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all ${
              !showSource
                ? "bg-white dark:bg-stone-700 text-stone-700 dark:text-stone-200 shadow-sm"
                : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-300"
            }`}
          >
            <Eye size={13} />
            <span>{t("documents.preview")}</span>
          </button>
          <button
            onClick={() => setShowSource(true)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all ${
              showSource
                ? "bg-white dark:bg-stone-700 text-stone-700 dark:text-stone-200 shadow-sm"
                : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-300"
            }`}
          >
            <Code size={13} />
            <span>{t("documents.source")}</span>
          </button>
        </div>
      </div>

      {/* HTML content */}
      <div className="flex-1 overflow-hidden">
        {showSource ? (
          <pre className="w-full h-full overflow-auto p-4 text-[13px] leading-relaxed bg-[#fafafa] dark:bg-[#1e1e1e] text-stone-700 dark:text-stone-300 font-mono">
            <code>{content}</code>
          </pre>
        ) : (
          <iframe
            srcDoc={content}
            title={t("documents.htmlDocument")}
            className="w-full h-full border-0"
            sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-modals"
          />
        )}
      </div>
    </div>
  );
});

export default HtmlPreview;
