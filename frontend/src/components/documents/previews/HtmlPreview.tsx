import { memo, useState, useEffect, useMemo, useRef } from "react";
import { Code, Eye, Search } from "lucide-react";
import { ToolbarIconButton } from "../../common";
import { useCodeMirrorReady } from "../../../hooks/useCodeMirrorReady";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { DeferredCodeMirrorViewer } from "../../common/DeferredCodeMirrorViewer";
import { useTranslation } from "react-i18next";
import { prepareHtmlPreviewContent } from "./htmlPreviewContent";

interface HtmlPreviewProps {
  content: string; // HTML content directly
}

const HtmlPreview = memo(function HtmlPreview({ content }: HtmlPreviewProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [showSource, setShowSource] = useState(false);
  const previewRef = useRef<HTMLDivElement>(null);
  const searchReady = useCodeMirrorReady(previewRef, showSource);
  const previewContent = useMemo(
    () => prepareHtmlPreviewContent(content),
    [content],
  );

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
    <div
      ref={previewRef}
      className="h-full w-full flex flex-col bg-white dark:bg-stone-900"
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 px-3 py-1.5 bg-stone-50 dark:bg-stone-900 border-b border-stone-200 dark:border-stone-700 shrink-0">
        <div className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden">
          <span
            className="w-2.5 h-2.5 rounded-full bg-emerald-400 shrink-0"
            aria-hidden="true"
          />
          <span className="truncate text-12 text-stone-500 dark:text-stone-400">
            {t("documents.htmlDocument")}
          </span>
          <span className="hidden sm:inline text-11 text-stone-400 dark:text-stone-500 tabular-nums">
            {content.length.toLocaleString()} chars
          </span>
        </div>

        <div className="flex shrink-0 items-center gap-0.5 bg-stone-100 dark:bg-stone-800 rounded-md p-0.5">
          {showSource && (
            <ToolbarIconButton
              disabled={!searchReady}
              title={t("common.search")}
              aria-label={t("common.search")}
              icon={<Search size={14} />}
              onClick={() => {
                const editor =
                  previewRef.current?.querySelector<HTMLElement>(".cm-editor");
                if (!editor) return;
                void import("../../common/codeMirrorSearchExtensions").then(
                  ({ openCodeMirrorSearch }) => openCodeMirrorSearch(editor),
                );
              }}
            />
          )}
          <button
            aria-label={t("documents.preview")}
            aria-pressed={!showSource}
            onClick={() => setShowSource(false)}
            className={`flex min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 items-center justify-center gap-1.5 px-2.5 py-1 rounded text-12 font-medium transition-all motion-reduce:transition-none ${
              !showSource
                ? "bg-white dark:bg-stone-700 text-stone-700 dark:text-stone-200 shadow-sm"
                : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-300"
            }`}
          >
            <Eye size={13} />
            <span className="hidden sm:inline">{t("documents.preview")}</span>
          </button>
          <button
            aria-label={t("documents.source")}
            aria-pressed={showSource}
            onClick={() => setShowSource(true)}
            className={`flex min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 items-center justify-center gap-1.5 px-2.5 py-1 rounded text-12 font-medium transition-all motion-reduce:transition-none ${
              showSource
                ? "bg-white dark:bg-stone-700 text-stone-700 dark:text-stone-200 shadow-sm"
                : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-300"
            }`}
          >
            <Code size={13} />
            <span className="hidden sm:inline">{t("documents.source")}</span>
          </button>
        </div>
      </div>

      {/* HTML content */}
      <div className="flex-1 overflow-hidden">
        {showSource ? (
          <DeferredCodeMirrorViewer
            value={content}
            language="html"
            lineNumbers={true}
            fontSize="0.8125rem"
            className="w-full h-full code-editor--overlay-search"
            showToolbar={false}
            simpleSearch
          />
        ) : (
          <iframe
            srcDoc={previewContent}
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
