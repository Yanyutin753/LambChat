import { memo, useMemo } from "react";
import { DeferredCodeMirrorViewer } from "../../common/DeferredCodeMirrorViewer";

interface CodeRendererProps {
  content: string;
  language?: string;
  filePath?: string;
  t?: (key: string, options?: Record<string, unknown>) => string;
  initialLine?: number;
}

const MAX_LINES = 10000;

// Memoized code renderer for better performance
const CodeRenderer = memo(function CodeRenderer({
  content,
  language,
  filePath,
  t,
  initialLine,
}: CodeRendererProps) {
  const displayContent = useMemo(() => {
    const lines = content.split("\n");
    if (lines.length > MAX_LINES) {
      const suffix = t
        ? `\n\n${t("documents.fileTooLargeLines", { count: MAX_LINES })}`
        : `\n\nShowing first ${MAX_LINES.toLocaleString()} of ${lines.length.toLocaleString()} lines`;
      return lines.slice(0, MAX_LINES).join("\n") + suffix;
    }
    return content;
  }, [content, t]);

  return (
    <div className="relative h-full overflow-auto bg-theme-bg-code">
      <DeferredCodeMirrorViewer
        value={displayContent}
        language={language}
        filePath={filePath}
        lineNumbers={true}
        fontSize="0.875rem"
        className="h-full"
        startLine={initialLine}
        highlightLineRange={
          initialLine ? { from: initialLine, to: initialLine + 10 } : undefined
        }
      />
    </div>
  );
});

export default CodeRenderer;
