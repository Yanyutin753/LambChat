import { memo, useEffect, useMemo, useRef, useCallback, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import {
  EditorView,
  ViewPlugin,
  Decoration,
  DecorationSet,
  ViewUpdate,
  lineNumbers as cmLineNumbers,
} from "@codemirror/view";
import { RangeSetBuilder } from "@codemirror/state";
import type { EditorState } from "@codemirror/state";
import type { Extension } from "@codemirror/state";
import { oneDark } from "@codemirror/theme-one-dark";
import { CopyButton } from "./CopyButton";
import { getLangSupport } from "./getLangSupport";

const githubLight = EditorView.theme(
  {
    "&": {
      color: "#24292f",
      backgroundColor: "transparent",
    },
    ".cm-content": {
      caretColor: "#0969da",
    },
    ".cm-cursor, .cm-dropCursor": {
      borderLeftColor: "#0969da",
    },
    ".cm-activeLine": {
      backgroundColor: "rgba(234, 238, 242, 0.5)",
    },
    ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
      backgroundColor: "rgba(84, 174, 255, 0.3)",
    },
    ".cm-gutters": {
      backgroundColor: "#fafafa",
      color: "#8b949e",
      borderRight: "1px solid #d8dee4",
    },
    ".cm-lineNumbers .cm-gutterElement": {
      color: "#8b949e",
    },
    ".cm-keyword": { color: "#cf222e" },
    ".cm-operator": { color: "#57606a" },
    ".cm-variable": { color: "#953800" },
    ".cm-variableName": { color: "#0550ae" },
    ".cm-typeName": { color: "#953800" },
    ".cm-propertyName": { color: "#0550ae" },
    ".cm-string": { color: "#0a3069" },
    ".cm-number": { color: "#0550ae" },
    ".cm-comment": { color: "#6e7781", fontStyle: "italic" },
    ".cm-def": { color: "#8250df" },
    ".cm-tag": { color: "#116329" },
    ".cm-attributeName": { color: "#0550ae" },
    ".cm-meta": { color: "#0550ae" },
  },
  { dark: false },
);

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

export interface HighlightLineRange {
  /** 1-based start line number */
  from: number;
  /** 1-based end line number (inclusive) */
  to: number;
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
  /** 1-based line number offset for gutter display (e.g. 50 means first line shows "50") */
  startLine?: number;
  /** Highlight a range of lines with a subtle background */
  highlightLineRange?: HighlightLineRange;
  /** Show a copy button overlay on hover (default: false) */
  copyable?: boolean;
}

/** ViewPlugin that decorates highlighted lines with a background color */
function highlightPlugin(from: number, to: number, isDark: boolean) {
  return ViewPlugin.fromClass(
    class {
      decorations: DecorationSet;
      constructor(view: EditorView) {
        this.decorations = buildDecorations(view, from, to, isDark);
      }
      update(update: ViewUpdate) {
        if (update.docChanged || update.viewportChanged) {
          this.decorations = buildDecorations(update.view, from, to, isDark);
        }
      }
    },
    { decorations: (v) => v.decorations },
  );
}

function buildDecorations(
  view: EditorView,
  from: number,
  to: number,
  isDark: boolean,
): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>();
  const lineCount = view.state.doc.lines;
  const start = Math.max(1, from);
  const end = Math.min(lineCount, to);
  for (let i = start; i <= end; i++) {
    const line = view.state.doc.line(i);
    const deco = Decoration.line({
      attributes: {
        style: `background-color: ${
          isDark ? "rgba(251, 191, 36, 0.1)" : "rgba(251, 191, 36, 0.15)"
        }`,
      },
    });
    builder.add(line.from, line.from, deco);
  }
  return builder.finish();
}

function getSelectedText(state: EditorState): string {
  const selectedRanges = state.selection.ranges.filter(
    (range) => range.from !== range.to,
  );
  return selectedRanges
    .map((range) => state.sliceDoc(range.from, range.to))
    .join("\n");
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
  startLine,
  highlightLineRange,
  copyable,
}: CodeMirrorViewerProps) {
  const isDark = useIsDark();
  const viewRef = useRef<EditorView | null>(null);
  const wrapperClassName = ["h-full", className].filter(Boolean).join(" ");

  const handleCreateEditor = useCallback(
    (view: EditorView) => {
      viewRef.current = view;
      // Scroll to the highlighted start line after mount
      if (highlightLineRange) {
        const targetLine = Math.max(
          1,
          Math.min(highlightLineRange.from, view.state.doc.lines),
        );
        const line = view.state.doc.line(targetLine);
        view.dispatch({
          effects: EditorView.scrollIntoView(line.from, { y: "center" }),
        });
      }
    },
    [highlightLineRange],
  );

  // Scroll when highlightLineRange changes (e.g. after content loads)
  useEffect(() => {
    const view = viewRef.current;
    if (!view || !highlightLineRange) return;
    const targetLine = Math.max(
      1,
      Math.min(highlightLineRange.from, view.state.doc.lines),
    );
    const line = view.state.doc.line(targetLine);
    view.dispatch({
      effects: EditorView.scrollIntoView(line.from, { y: "center" }),
    });
  }, [highlightLineRange]);

  const extensions = useMemo(() => {
    const exts: Extension[] = [
      EditorView.editable.of(false),
      EditorView.domEventHandlers({
        copy: (event, view) => {
          const selectedText = getSelectedText(view.state);
          if (!selectedText || !event.clipboardData) {
            return false;
          }

          event.clipboardData.setData("text/plain", selectedText);
          event.preventDefault();
          return true;
        },
      }),
      EditorView.theme({
        "&": {
          height: "100%",
          fontSize,
          backgroundColor: `${isDark ? "#282c34" : "#ffffff"} !important`,
        },
        ".cm-editor": {
          height: "100%",
          backgroundColor: `${isDark ? "#282c34" : "#ffffff"} !important`,
        },
        ".cm-scroller": {
          height: "100%",
          overflow: "auto",
          backgroundColor: `${isDark ? "#282c34" : "#ffffff"} !important`,
          ...(maxHeight ? { maxHeight } : {}),
        },
        ".cm-content": {
          minHeight: "100% !important",
          backgroundColor: "transparent !important",
          userSelect: "text",
          cursor: "text",
        },
        ".cm-line": {
          userSelect: "text",
        },
        ".cm-selectionLayer .cm-selectionBackground, &.cm-focused .cm-selectionLayer .cm-selectionBackground":
          {
            backgroundColor: isDark
              ? "rgba(96, 165, 250, 0.46)"
              : "rgba(37, 99, 235, 0.26)",
          },
        ".cm-content ::selection": {
          backgroundColor: isDark
            ? "rgba(96, 165, 250, 0.46)"
            : "rgba(37, 99, 235, 0.26)",
        },
        ".cm-gutters, .cm-gutter": {
          minHeight: "100% !important",
          backgroundColor: `${isDark ? "#282c34" : "#fafafa"} !important`,
          borderRight: isDark ? "1px solid #333" : "1px solid #e7e5e4",
        },
        ".cm-lineNumbers .cm-gutterElement": {
          color: isDark ? "#6e7681" : "#78716c",
          userSelect: "none",
        },
      }),
    ];

    // Highlight plugin
    if (highlightLineRange) {
      exts.push(
        highlightPlugin(highlightLineRange.from, highlightLineRange.to, isDark),
      );
    }

    const lang = getLangSupport(language, filePath);
    if (lang) exts.push(lang);
    return exts;
  }, [language, filePath, fontSize, maxHeight, isDark, highlightLineRange]);

  // Build line number offset if startLine is provided
  const lineOffsetExtensions = useMemo(() => {
    if (startLine === undefined || startLine <= 1) return [];
    const lineOffset = startLine - 1;
    return [
      cmLineNumbers({
        formatNumber: (n: number) => String(n + lineOffset),
      }),
    ];
  }, [startLine]);

  return (
    <div className={copyable ? "group relative h-full" : wrapperClassName}>
      <div className={copyable ? wrapperClassName : undefined}>
        <CodeMirror
          className="h-full"
          height="100%"
          value={value}
          theme={isDark ? oneDark : githubLight}
          extensions={[...extensions, ...lineOffsetExtensions]}
          onCreateEditor={handleCreateEditor}
          basicSetup={{
            lineNumbers: !startLine || startLine <= 1 ? lineNumbers : false,
            highlightActiveLineGutter: false,
            highlightActiveLine: false,
            foldGutter: false,
            bracketMatching: false,
            closeBrackets: false,
            indentOnInput: false,
          }}
        />
      </div>
      {copyable && (
        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <CopyButton
            text={value}
            size={14}
            className="!bg-white/80 dark:!bg-stone-800/80 !rounded-md !border !border-stone-200 dark:!border-stone-700"
          />
        </div>
      )}
    </div>
  );
});

export default CodeMirrorViewer;
