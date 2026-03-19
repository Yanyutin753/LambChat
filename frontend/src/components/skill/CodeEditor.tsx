import { useRef, useCallback, useEffect, useState, memo } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import {
  oneDark,
  oneLight,
} from "react-syntax-highlighter/dist/esm/styles/prism";
import { detectLanguage } from "../documents/utils/detectLanguage";

interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  filePath?: string;
  placeholder?: string;
  className?: string;
}

const CodeEditor = memo(function CodeEditor({
  value,
  onChange,
  filePath,
  placeholder,
  className = "",
}: CodeEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const highlightRef = useRef<HTMLPreElement>(null);
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

  const language = filePath ? detectLanguage(filePath) : "markdown";

  const handleScroll = useCallback(() => {
    if (textareaRef.current && highlightRef.current) {
      highlightRef.current.scrollTop = textareaRef.current.scrollTop;
      highlightRef.current.scrollLeft = textareaRef.current.scrollLeft;
    }
  }, []);

  // Sync scroll from highlight to textarea
  const handleHighlightScroll = useCallback(() => {
    if (textareaRef.current && highlightRef.current) {
      textareaRef.current.scrollTop = highlightRef.current.scrollTop;
      textareaRef.current.scrollLeft = highlightRef.current.scrollLeft;
    }
  }, []);

  const codeStyle = isDark ? oneDark : oneLight;
  const bgColor = isDark ? "#282c34" : "#fafafa";

  return (
    <div className={`relative ${className}`}>
      {/* Syntax highlighted background */}
      <div
        className="absolute inset-0 overflow-hidden pointer-events-none"
        onScroll={handleHighlightScroll}
        ref={(el) => {
          if (el) {
            // Store the scroll container ref
            (highlightRef as React.MutableRefObject<HTMLPreElement | HTMLDivElement>).current = el as HTMLDivElement;
          }
        }}
      >
        <SyntaxHighlighter
          language={language}
          style={codeStyle}
          customStyle={{
            margin: 0,
            padding: "1rem",
            background: bgColor,
            fontSize: "0.875rem",
            lineHeight: "1.6",
            minHeight: "100%",
          }}
          showLineNumbers
          lineNumberStyle={{
            minWidth: "2.5em",
            paddingRight: "1em",
            textAlign: "right" as const,
            color: isDark ? "#6b7280" : "#9ca3af",
            userSelect: "none" as const,
            fontSize: "0.75rem",
          }}
          codeTagProps={{
            style: {
              fontFamily:
                'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
            },
          }}
          wrapLines={false}
          wrapLongLines={false}
        >
          {value || " "}
        </SyntaxHighlighter>
      </div>

      {/* Transparent textarea overlay */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onScroll={handleScroll}
        placeholder={placeholder}
        spellCheck={false}
        className="absolute inset-0 w-full h-full resize-none bg-transparent text-transparent caret-stone-300 dark:caret-stone-400 font-mono text-sm focus:outline-none"
        style={{
          padding: "1rem",
          paddingLeft: "2.5rem + 1rem",
          fontSize: "0.875rem",
          lineHeight: "1.6",
          tabSize: 2,
          fontFamily:
            'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
          // Ensure textarea matches highlighter layout
          letterSpacing: "normal",
          wordSpacing: "normal",
        }}
      />
    </div>
  );
});

export default CodeEditor;
