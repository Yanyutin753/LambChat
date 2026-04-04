import { memo, useMemo } from "react";

interface PlainTextViewerProps {
  content: string;
}

const MAX_LINES = 10000;

const PlainTextViewer = memo(function PlainTextViewer({
  content,
}: PlainTextViewerProps) {
  const lines = useMemo(() => {
    const allLines = content.split("\n");
    if (allLines.length > MAX_LINES) {
      return allLines.slice(0, MAX_LINES);
    }
    return allLines;
  }, [content]);

  const isTruncated = content.split("\n").length > MAX_LINES;

  // Calculate line number width based on max line count
  const lineCount = lines.length;
  const lineNumberWidth =
    lineCount >= 1000
      ? "4rem" // ~4 digits
      : lineCount >= 100
        ? "3rem" // ~3 digits
        : "2rem"; // ~2 digits

  return (
    <div className="h-full overflow-auto bg-stone-100 dark:bg-[#282c34] p-4 sm:p-6">
      <pre
        className="text-xs sm:text-sm leading-relaxed font-mono m-0"
        style={{
          fontFamily:
            'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
        }}
      >
        {lines.map((line, i) => (
          <div key={i} className="flex">
            <span
              className="select-none shrink-0 text-right pr-4 border-r border-stone-300 dark:border-stone-600 text-stone-400 dark:text-stone-600"
              style={{ width: lineNumberWidth }}
            >
              {i + 1}
            </span>
            <span className="whitespace-pre text-stone-800 dark:text-stone-200 ml-4">
              {line}
            </span>
          </div>
        ))}
        {isTruncated && (
          <div className="mt-2 text-stone-400 dark:text-stone-500 text-xs">
            ... ({MAX_LINES} lines shown)
          </div>
        )}
      </pre>
    </div>
  );
});

export default PlainTextViewer;
