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
        {/* Status */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-stone-500 dark:text-stone-400">
            {t("documents.htmlDocument")}
          </span>
          <span className="text-xs text-stone-400 dark:text-stone-500">
            ({t("documents.chars", { count: content.length })})
          </span>
        </div>

        {/* Actions */}
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

      {/* HTML content */}
      <div className="flex-1 overflow-hidden">
        {showSource ? (
          <pre className="w-full h-full overflow-auto p-4 text-sm bg-stone-50 dark:bg-stone-800 text-stone-700 dark:text-stone-300 font-mono">
            <code>{content}</code>
          </pre>
        ) : (
          // 使用 sandboxed iframe 隔离 CSS，同时允许 JavaScript 和外部资源
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
