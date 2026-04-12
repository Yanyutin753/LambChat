import { memo, useEffect, useMemo, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView } from "@codemirror/view";
import type { Extension } from "@codemirror/state";
import { oneDark } from "@codemirror/theme-one-dark";
import { getLangSupport } from "./getLangSupport";

// Shared hook for detecting dark mode via MutationObserver
function useIsDark() {
  const [isDark, setIsDark] = useState(() =>
    typeof document !== "undefined"
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

  return isDark;
}

export interface CodeMirrorViewerProps {
  /** The code content to display */
  value: string;
  /** CodeMirror language name (e.g. "typescript", "python") */
  language?: string;
  /** File path – used to auto-detect language when `language` is not provided */
  filePath?: string;
  /** Show line numbers (default: true) */
  lineNumbers?: boolean;
  /** Maximum height in CSS value (e.g. "256px", "16rem"). Enables vertical scroll. */
  maxHeight?: string;
  /** Additional CSS class for the wrapper */
  className?: string;
  /** Font size override (default: "0.75rem") */
  fontSize?: string;
}

/**
 * A read-only CodeMirror viewer for rendering code with syntax highlighting.
 * Supports dark mode auto-switching, line numbers, and max-height scrolling.
 */
export const CodeMirrorViewer = memo(function CodeMirrorViewer({
  value,
  language,
  filePath,
  lineNumbers = true,
  maxHeight,
  className,
  fontSize = "0.75rem",
}: CodeMirrorViewerProps) {
  const isDark = useIsDark();

  const extensions = useMemo(() => {
    const exts: Extension[] = [
      EditorView.editable.of(false),
      EditorView.theme({
        "&": {
          fontSize,
          backgroundColor: "transparent",
        },
        ".cm-scroller": {
          ...(maxHeight ? { maxHeight, overflow: "auto" } : {}),
        },
        ".cm-gutters": {
          borderRight: isDark ? "1px solid #333" : "1px solid #e7e5e4",
        },
        ".cm-lineNumbers .cm-gutterElement": {
          color: isDark ? "#6e7681" : "#78716c",
          userSelect: "none",
        },
      }),
    ];
    const lang = getLangSupport(language, filePath);
    if (lang) exts.push(lang);
    return exts;
  }, [language, filePath, fontSize, maxHeight, isDark]);

  return (
    <div className={className}>
      <CodeMirror
        value={value}
        theme={isDark ? oneDark : undefined}
        extensions={extensions}
        basicSetup={{
          lineNumbers,
          highlightActiveLineGutter: false,
          highlightActiveLine: false,
          foldGutter: false,
          bracketMatching: false,
          closeBrackets: false,
          indentOnInput: false,
        }}
      />
    </div>
  );
});

export default CodeMirrorViewer;
