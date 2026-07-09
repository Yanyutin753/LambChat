import { useState, useEffect, useMemo } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView } from "@codemirror/view";
import { oneDark } from "@codemirror/theme-one-dark";
import { getLangSupport } from "../common/getLangSupport";

export function SkillEditor({
  value,
  onChange,
  className,
  filePath,
  readOnly,
  lineWrapping = true,
}: {
  value: string;
  onChange: (val: string) => void;
  className?: string;
  filePath?: string;
  readOnly?: boolean;
  lineWrapping?: boolean;
}) {
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

  const extensions = useMemo(() => {
    const langSupport = getLangSupport(undefined, filePath);

    return [
      ...(langSupport ? [langSupport] : []),
      ...(lineWrapping ? [EditorView.lineWrapping] : []),
      EditorView.theme({
        "&": {
          height: "100%",
          fontSize: "0.875rem",
        },
        ".cm-editor": {
          height: "100%",
        },
        ".cm-scroller": {
          overflow: "auto",
        },
        ".cm-content": {
          minHeight: "100%",
          backgroundColor: "transparent !important",
          userSelect: "text",
          caretColor: isDark ? "#93c5fd" : "#2563eb",
        },
        ".cm-cursor, .cm-dropCursor": {
          borderLeftColor: isDark ? "#93c5fd" : "#2563eb",
          borderLeftWidth: "2px",
        },
        ".cm-focused": {
          outline: "none",
          boxShadow: `inset 0 0 0 1px ${
            isDark ? "rgba(147, 197, 253, 0.34)" : "rgba(37, 99, 235, 0.22)"
          }`,
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
        ".cm-lineNumbers .cm-gutterElement": {
          userSelect: "none",
        },
      }),
    ];
  }, [filePath, isDark, lineWrapping]);

  return (
    <div
      className={`${
        className || ""
      } h-full min-h-0 flex flex-col overflow-hidden [&_.cm-theme]:h-full [&_.cm-editor]:h-full [&_.cm-editor]:min-h-0 [&_.cm-scroller]:flex-1 [&_.cm-scroller]:min-h-0 [&_.cm-scroller]:overflow-auto`}
    >
      <CodeMirror
        value={value}
        onChange={onChange}
        theme={isDark ? oneDark : undefined}
        extensions={extensions}
        readOnly={readOnly}
        editable={!readOnly}
        basicSetup={{
          lineNumbers: true,
          highlightActiveLineGutter: true,
          highlightActiveLine: true,
          foldGutter: true,
          searchKeymap: true,
          bracketMatching: true,
          closeBrackets: true,
          indentOnInput: true,
        }}
        className="min-h-0 flex-1"
      />
    </div>
  );
}
