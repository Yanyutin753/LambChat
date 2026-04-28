import { memo, useEffect, useMemo, useRef, useCallback, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import {
  EditorView,
  ViewPlugin,
  Decoration,
  DecorationSet,
  ViewUpdate,
  WidgetType,
} from "@codemirror/view";
import { RangeSetBuilder } from "@codemirror/state";
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
}: CodeMirrorViewerProps) {
  const isDark = useIsDark();
  const viewRef = useRef<EditorView | null>(null);

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
  // We pass it via basicSetup replacement — since @uiw/react-codemirror doesn't
  // support line number offset directly, we handle it via theme gutter element style
  // Actually, we use a ViewPlugin to replace gutter element text content
  const lineOffsetExtensions = useMemo(() => {
    if (startLine === undefined || startLine <= 1) return [];
    const lineOffset = startLine - 1;
    return [
      EditorView.theme({
        ".cm-lineNumbers .cm-gutterElement": {
          // Line number offset is handled by prepending to display
        },
      }),
      ViewPlugin.fromClass(
        class {
          decorations: DecorationSet;
          constructor(view: EditorView) {
            this.decorations = this.build(view);
          }
          update(update: ViewUpdate) {
            if (update.docChanged || update.viewportChanged) {
              this.decorations = this.build(update.view);
            }
          }
          build(view: EditorView): DecorationSet {
            const builder = new RangeSetBuilder<Decoration>();
            const count = view.state.doc.lines;
            for (let i = 1; i <= count; i++) {
              const line = view.state.doc.line(i);
              const deco = Decoration.widget({
                widget: new (class extends WidgetType {
                  toDOM() {
                    const span = document.createElement("span");
                    span.textContent = String(i + lineOffset);
                    return span;
                  }
                })(),
                side: -1,
                block: false,
              });
              builder.add(line.from, line.from, deco);
            }
            return builder.finish();
          }
        },
        { decorations: (v) => v.decorations },
      ),
    ];
  }, [startLine]);

  return (
    <div className={className}>
      <CodeMirror
        value={value}
        theme={isDark ? oneDark : undefined}
        extensions={[...extensions, ...lineOffsetExtensions]}
        onCreateEditor={handleCreateEditor}
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
