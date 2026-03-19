import { memo, useEffect, useMemo, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView } from "@codemirror/view";
import type { Extension } from "@codemirror/state";
import { oneDark } from "@codemirror/theme-one-dark";
import { markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { yaml } from "@codemirror/lang-yaml";
import { json } from "@codemirror/lang-json";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { sql } from "@codemirror/lang-sql";

// Map a language name (from markdown fenced code blocks) or file extension to a CodeMirror language support.
// Returns `undefined` for unknown languages (CodeMirror will use plain text).
export function getLangSupport(
  language?: string,
  filePath?: string,
): Extension | undefined {
  // Prefer explicit language name from code blocks
  const lang = language?.toLowerCase() || "";
  const ext = filePath
    ? filePath.split(".").pop()?.toLowerCase() ?? ""
    : "";

  // Map language names from markdown fences (e.g. ```typescript, ```py)
  const langMap: Record<string, () => Extension> = {
    js: () => javascript({ jsx: true }),
    jsx: () => javascript({ jsx: true }),
    javascript: () => javascript({ jsx: true }),
    ts: () => javascript({ jsx: true, typescript: true }),
    tsx: () => javascript({ jsx: true, typescript: true }),
    typescript: () => javascript({ jsx: true, typescript: true }),
    py: () => python(),
    python: () => python(),
    md: () => markdown({ base: markdownLanguage }),
    markdown: () => markdown({ base: markdownLanguage }),
    yaml: () => yaml(),
    yml: () => yaml(),
    json: () => json(),
    html: () => html(),
    htm: () => html(),
    css: () => css(),
    scss: () => css(),
    less: () => css(),
    sql: () => sql(),
  };

  // Also map by file extension when no explicit language is given
  if (!lang && ext) {
    return langMap[ext]?.();
  }

  return langMap[lang]?.();
}

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
          borderRight: isDark
            ? "1px solid #44403c"
            : "1px solid #e7e5e4",
        },
        ".cm-lineNumbers .cm-gutterElement": {
          color: isDark ? "#71717a" : "#a1a1aa",
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
