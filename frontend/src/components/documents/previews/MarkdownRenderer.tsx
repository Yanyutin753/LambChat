import { memo, useMemo } from "react";
import { MarkdownContent } from "../../chat/ChatMessage/MarkdownContent";

interface MarkdownRendererProps {
  content: string;
  _t: (key: string, options?: Record<string, unknown>) => string;
}

// Reuse MarkdownContent to avoid maintaining two separate markdown renderers
const MarkdownRenderer = memo(function MarkdownRenderer({
  content,
}: MarkdownRendererProps) {
  // Limit content for very large files
  const displayContent = useMemo(() => {
    const MAX_CHARS = 500000;
    if (content.length > MAX_CHARS) {
      return content.slice(0, MAX_CHARS) + "\n\n... (content truncated)";
    }
    return content;
  }, [content]);

  return (
    <div className="markdown-preview overflow-auto h-full">
      <div className="document-reading-column">
        <MarkdownContent content={displayContent} />
      </div>
    </div>
  );
});

export default MarkdownRenderer;
