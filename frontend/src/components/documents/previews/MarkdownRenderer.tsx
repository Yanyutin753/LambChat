import { memo, useMemo } from "react";
import { MarkdownContent } from "../../chat/ChatMessage/MarkdownContent";

interface MarkdownRendererProps {
  content: string;
  _t: (key: string, options?: Record<string, unknown>) => string;
}

// Reuse MarkdownContent to avoid maintaining two separate markdown renderers
const MarkdownRenderer = memo(function MarkdownRenderer({
  content,
  _t,
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
    <div className="markdown-preview overflow-auto h-full p-4 sm:p-6 lg:p-8">
      <MarkdownContent content={displayContent} />
    </div>
  );
});

export default MarkdownRenderer;
