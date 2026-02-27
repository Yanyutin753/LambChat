import { memo, useEffect, useMemo, useState } from "react";
import { FileText, Loader2, AlertCircle } from "lucide-react";
import mammoth from "mammoth";

interface WordPreviewProps {
  arrayBuffer: ArrayBuffer;
  t: (key: string, options?: Record<string, unknown>) => string;
}

// Custom styles for Word document content
const wordContentStyles = `
  .word-preview-content {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    line-height: 1.7;
    color: #1f2937;
  }
  .word-preview-content.dark {
    color: #e5e7eb;
  }
  .word-preview-content h1 {
    font-size: 2rem;
    font-weight: 700;
    margin: 1.5rem 0 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #e5e7eb;
  }
  .dark .word-preview-content h1 {
    border-bottom-color: #374151;
  }
  .word-preview-content h2 {
    font-size: 1.5rem;
    font-weight: 600;
    margin: 1.25rem 0 0.75rem;
    padding-bottom: 0.25rem;
    border-bottom: 1px solid #e5e7eb;
  }
  .dark .word-preview-content h2 {
    border-bottom-color: #374151;
  }
  .word-preview-content h3 {
    font-size: 1.25rem;
    font-weight: 600;
    margin: 1rem 0 0.5rem;
  }
  .word-preview-content h4, .word-preview-content h5, .word-preview-content h6 {
    font-size: 1.125rem;
    font-weight: 600;
    margin: 0.75rem 0 0.5rem;
  }
  .word-preview-content p {
    margin: 0.75rem 0;
  }
  .word-preview-content ul, .word-preview-content ol {
    margin: 0.75rem 0;
    padding-left: 1.5rem;
  }
  .word-preview-content li {
    margin: 0.25rem 0;
  }
  .word-preview-content ul {
    list-style-type: disc;
  }
  .word-preview-content ol {
    list-style-type: decimal;
  }
  .word-preview-content blockquote {
    margin: 1rem 0;
    padding: 0.75rem 1rem;
    border-left: 4px solid #f59e0b;
    background: #fffbeb;
    border-radius: 0 0.5rem 0.5rem 0;
  }
  .dark .word-preview-content blockquote {
    background: rgba(245, 158, 11, 0.1);
    border-left-color: #fbbf24;
  }
  .word-preview-content table {
    width: 100%;
    margin: 1rem 0;
    border-collapse: collapse;
    border-radius: 0.5rem;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }
  .word-preview-content th {
    background: #f9fafb;
    padding: 0.75rem 1rem;
    text-align: left;
    font-weight: 600;
    border-bottom: 2px solid #e5e7eb;
  }
  .dark .word-preview-content th {
    background: #1f2937;
    border-bottom-color: #374151;
  }
  .word-preview-content td {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid #e5e7eb;
  }
  .dark .word-preview-content td {
    border-bottom-color: #374151;
  }
  .word-preview-content tr:hover td {
    background: #f9fafb;
  }
  .dark .word-preview-content tr:hover td {
    background: #1f2937;
  }
  .word-preview-content img {
    max-width: 100%;
    height: auto;
    margin: 1rem 0;
    border-radius: 0.5rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  }
  .word-preview-content a {
    color: #2563eb;
    text-decoration: underline;
  }
  .dark .word-preview-content a {
    color: #60a5fa;
  }
  .word-preview-content a:hover {
    color: #1d4ed8;
  }
  .dark .word-preview-content a:hover {
    color: #93c5fd;
  }
  .word-preview-content code {
    font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
    font-size: 0.875em;
    background: #f3f4f6;
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
    color: #be185d;
  }
  .dark .word-preview-content code {
    background: #374151;
    color: #f472b6;
  }
  .word-preview-content pre {
    background: #1f2937;
    color: #e5e7eb;
    padding: 1rem;
    border-radius: 0.5rem;
    overflow-x: auto;
    margin: 1rem 0;
  }
  .word-preview-content pre code {
    background: transparent;
    padding: 0;
    color: inherit;
  }
  .word-preview-content hr {
    border: none;
    height: 1px;
    background: linear-gradient(to right, transparent, #e5e7eb, transparent);
    margin: 1.5rem 0;
  }
  .dark .word-preview-content hr {
    background: linear-gradient(to right, transparent, #374151, transparent);
  }
`;

const WordPreview = memo(function WordPreview({
  arrayBuffer,
  t,
}: WordPreviewProps) {
  const [html, setHtml] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Detect dark mode
  const [isDark, setIsDark] = useState(() =>
    typeof window !== "undefined"
      ? document.documentElement.classList.contains("dark")
      : false,
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

  // Add custom styles
  useEffect(() => {
    const styleId = "word-preview-styles";
    if (!document.getElementById(styleId)) {
      const style = document.createElement("style");
      style.id = styleId;
      style.textContent = wordContentStyles;
      document.head.appendChild(style);
    }
  }, []);

  useEffect(() => {
    const convertWord = async () => {
      try {
        const result = await mammoth.convertToHtml(
          { arrayBuffer },
          {
            styleMap: [
              "p[style-name='Heading 1'] => h1:fresh",
              "p[style-name='Heading 2'] => h2:fresh",
              "p[style-name='Heading 3'] => h3:fresh",
              "p[style-name='Heading 4'] => h4:fresh",
              "b => strong",
              "i => em",
              "u => u",
            ],
          },
        );
        setHtml(result.value);
        setError(null);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : t("documents.wordConversionError"),
        );
      } finally {
        setLoading(false);
      }
    };
    convertWord();
  }, [arrayBuffer, t]);

  const processedHtml = useMemo(() => {
    if (!html) return "";
    // Add wrapper class for styling
    return html;
  }, [html]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[300px] gap-4">
        <div className="relative">
          <Loader2 size={40} className="animate-spin text-amber-500" />
          <div className="absolute inset-0 animate-ping opacity-20">
            <Loader2 size={40} className="text-amber-500" />
          </div>
        </div>
        <p className="text-sm text-stone-500 dark:text-stone-400">
          {t("documents.loading") || "Loading document..."}
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[300px] p-6">
        <div className="max-w-md w-full">
          <div className="flex items-center gap-3 p-4 mb-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
            <AlertCircle size={24} className="text-red-500 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-red-600 dark:text-red-400">
                {t("documents.wordPreviewError")}
              </p>
              <p className="text-xs text-red-500 dark:text-red-400/80 mt-1">
                {error}
              </p>
            </div>
          </div>
          <div className="flex items-center justify-center gap-2 text-stone-400 dark:text-stone-500">
            <FileText size={16} />
            <span className="text-xs">
              {t("documents.supportedFormats") || "Word documents (.docx)"}
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto bg-white dark:bg-stone-900">
      <div className="max-w-4xl mx-auto">
        {/* Document content */}
        <div className="px-6 py-4 pb-8">
          <div
            className={`word-preview-content ${isDark ? "dark" : ""}`}
            dangerouslySetInnerHTML={{ __html: processedHtml }}
          />
        </div>
      </div>
    </div>
  );
});

export default WordPreview;
