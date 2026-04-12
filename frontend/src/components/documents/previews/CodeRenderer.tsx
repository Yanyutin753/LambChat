import { memo, useMemo } from "react";
import { CodeMirrorViewer } from "../../common/CodeMirrorViewer";

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

  return (
    <div className="relative h-full overflow-auto bg-stone-100 dark:bg-[#1e1e1e] [&_.cm-editor]:h-full [&_.cm-scroller]:!overflow-auto">
      <CodeMirrorViewer
        value={displayContent}
        language={language}
        lineNumbers={true}
        fontSize="0.875rem"
        className="h-full"
      />
    </div>
  );
});

export default CodeRenderer;
